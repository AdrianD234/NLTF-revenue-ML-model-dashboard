"""Materialised Treasury-macro and conflict/fuel replay results.

Both replays are pure functions of the promoted pack and the governed model
state: ``run_direct_treasury_scenario_replay`` and
``run_fuel_price_scenario_replay`` take no UI control, and their Streamlit
caches are keyed on the pack signature alone.  Profiling on the PR #15 merge
commit measured them at 7.9 s and 44.0 s respectively - together ~52 s of the
~57 s cold Revenue Outlook path - because they load joblib fitted state and
re-run forward forecasting (25 ``vnext_forward_forecast`` calls, plus
``ar1_engine.fit_production_state``) on the first render of every process.

Nothing about that work depends on what the reader selected, so it is computed
once offline and committed.  The runtime reconstructs the exact dataclasses
from Arrow/Parquet, so every downstream consumer - the overlay chain, the
policy pair factors, the conflict traces, the audit surfaces - sees byte-
identical frames and no governed value moves.

The cache is deliberately NOT a scenario cube.  It has no scenario dimension
at all: one entry per (engine, pack digest).

Fail-closed by contract: a missing, stale or corrupt cache raises with the
rebuild command rather than silently serving old numbers or silently falling
back to the 52 s path.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

__all__ = [
    "REPLAY_CACHE_SCHEMA_VERSION",
    "ReplayCacheError",
    "ReplayCacheMissing",
    "ReplayCacheStale",
    "build_replay_cache",
    "load_replay_cache",
    "replay_cache_dir",
    "replay_cache_source_digest",
    "replay_cache_status",
]

# Bumped whenever the on-disk layout or the encoding changes.  A mismatch is a
# stale cache, not a soft warning.
REPLAY_CACHE_SCHEMA_VERSION = "1"
BUILDER_VERSION = "1"

_CACHE_ROOT = Path("data") / "revenue_outlook_replay_cache"
_REBUILD_COMMAND = "python scripts/build_revenue_outlook_replay_cache.py --engine {engine}"

# Every non-pack input the two replays read, captured with a `sys.addaudithook`
# open-trace over a full replay run rather than guessed.  Engine-specific
# entries are templated on {engine_dir}.  Paths that do not exist are recorded
# as absent, which is itself part of the digest: a source appearing later
# invalidates the cache.
_SOURCE_FILES: tuple[str, ...] = (
    "data/current_revenue_outlook/conflict_fuel_price_scenarios.csv",
    "data/current_revenue_outlook/conflict_gdp_calibration.csv",
    "data/current_revenue_outlook/sensitivity_seed_inputs.csv",
    "data/current_revenue_outlook/treasury_befu26_macro_path.csv",
    "data/dashboard_evidence_pack/data/component_predictions.parquet",
    "data/dashboard_evidence_pack/data/scorecard_predictions.parquet",
    "data/model_input_history/heavy_ruc_inputs.parquet",
    "data/model_input_history/light_ruc_inputs.parquet",
    "data/model_input_history/manifest.json",
    "data/model_input_history/ped_inputs.parquet",
    "data/revenue_model_source_pack/2026_05_19/fed_rate_paths.csv",
    "data/vfm_202405/vfm_vkt_shares.csv",
)

# Directories whose entire contents are inputs: the promoted fitted state the
# replays load, and the official vintage spines.  Hashed as a whole so a file
# ADDED to one of them also invalidates the cache.
_SOURCE_TREES: tuple[str, ...] = (
    "data/dashboard_evidence_pack_reproducibility",
    "data/revenue_model_source_pack/official_vintages",
)

_ENGINE_SOURCE_FILES: dict[str, tuple[str, ...]] = {
    "ar1": ("data/engine_ar1/dashboard_evidence_pack/data/finalists.parquet",),
    "ensemble": ("data/dashboard_evidence_pack/data/finalists.parquet",),
}


class ReplayCacheError(RuntimeError):
    """Base class: the compiled replay cache cannot be trusted."""


class ReplayCacheMissing(ReplayCacheError):
    """No compiled replay cache exists for this engine."""


class ReplayCacheStale(ReplayCacheError):
    """A compiled cache exists but its sources have moved underneath it."""


# ---------------------------------------------------------------------------
# dtype-faithful frame encoding
# ---------------------------------------------------------------------------
# Several replay lineage frames carry object columns holding a MIX of Python
# floats and strings (`real_petrol_price_cents_per_litre` is the live case:
# some cells are 189.9375, others "189.9375").  Arrow rejects those outright.
# Rather than coerce - which would silently rewrite an audit value - each mixed
# column is stored as text beside a companion column recording the element type,
# and rebuilt cell by cell on load.  `repr` round-trips Python floats exactly,
# so the reconstruction is lossless.

_OBJKIND_SUFFIX = "__objkind"


def _element_kind(value: Any) -> str:
    # The three null flavours are NOT interchangeable: an object column mixing
    # floats with ``pd.NA`` compares unequal to the same column holding
    # ``None``, so each is recorded distinctly and restored as itself.
    if value is None:
        return "none"
    if value is pd.NA:
        return "na"
    if value is pd.NaT:
        return "nat"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, np.bool_):
        return "bool_"
    if isinstance(value, str):
        return "str"
    if isinstance(value, np.float64):
        return "float64_nan" if pd.isna(value) else "float64"
    if isinstance(value, float):
        return "nan" if pd.isna(value) else "float"
    if isinstance(value, np.integer):
        return "int64"
    if isinstance(value, int):
        return "int"
    return "str"


_NULL_KINDS = {"none", "na", "nat", "nan", "float64_nan"}


def _encode_element(value: Any, kind: str) -> str:
    if kind in _NULL_KINDS:
        return ""
    if kind in {"float", "float64"}:
        return repr(float(value))
    if kind in {"bool", "bool_"}:
        return "True" if bool(value) else "False"
    if kind in {"int", "int64"}:
        return str(int(value))
    return str(value)


def _decode_element(text: Any, kind: str) -> Any:
    if kind == "none":
        return None
    if kind == "na":
        return pd.NA
    if kind == "nat":
        return pd.NaT
    if kind == "nan":
        return float("nan")
    if kind == "float64_nan":
        return np.float64("nan")
    if kind == "float":
        return float(text)
    if kind == "float64":
        return np.float64(text)
    if kind == "int":
        return int(text)
    if kind == "int64":
        return np.int64(text)
    if kind == "bool":
        return text == "True"
    if kind == "bool_":
        return np.bool_(text == "True")
    return str(text)


def _object_columns(frame: pd.DataFrame) -> list[str]:
    """Every object-dtype column, not merely the type-mixed ones.

    Arrow cannot preserve an object column's identity in any of the three
    shapes these frames use: mixed float/str cells are rejected outright, an
    all-``None`` column comes back as a typed null column, and a
    uniformly-float object column comes back as ``float64``.  All three would
    change a governed frame's dtype on reload, so all three are encoded.
    """
    return [str(column) for column in frame.columns if frame[column].dtype == object]


def _encode_frame(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Return an Arrow-safe frame plus the metadata needed to invert it."""
    encoded = frame.copy()
    mixed = _object_columns(encoded)
    for column in mixed:
        values = encoded[column].tolist()
        kinds = [_element_kind(value) for value in values]
        encoded[column] = [
            _encode_element(value, kind) for value, kind in zip(values, kinds, strict=True)
        ]
        encoded[column] = encoded[column].astype("string")
        encoded[f"{column}{_OBJKIND_SUFFIX}"] = pd.array(kinds, dtype="string")
    index_column = None
    if not isinstance(encoded.index, pd.RangeIndex) or encoded.index.start != 0 or encoded.index.step != 1:
        index_column = "__replay_cache_index__"
        encoded = encoded.reset_index(names=index_column)
    meta = {
        "object_columns": mixed,
        "index_column": index_column,
        "index_name": frame.index.name,
        # Some factor frames come out of a groupby/pivot with a NAMED columns
        # index ("scenario_name"). Arrow does not carry that, and
        # assert_frame_equal treats it as a difference.
        "columns_name": frame.columns.name,
        "columns": [str(column) for column in frame.columns],
        "dtypes": {str(column): str(dtype) for column, dtype in frame.dtypes.items()},
        "rows": int(len(frame)),
    }
    return encoded, meta


def _decode_frame(frame: pd.DataFrame, meta: dict[str, Any]) -> pd.DataFrame:
    columns = [str(column) for column in meta.get("columns", [])]
    dtypes = {str(k): str(v) for k, v in meta.get("dtypes", {}).items()}

    # A frame that was empty on both axes carries no Arrow schema worth
    # trusting; rebuild it from the recorded contract instead.
    if not columns:
        return pd.DataFrame()

    decoded = frame
    index_column = meta.get("index_column")
    if index_column and index_column in decoded.columns:
        decoded = decoded.set_index(index_column)
        decoded.index.name = meta.get("index_name")

    for column in meta.get("object_columns", []):
        kind_column = f"{column}{_OBJKIND_SUFFIX}"
        texts = decoded[column].tolist()
        kinds = decoded[kind_column].tolist()
        decoded[column] = pd.Series(
            [
                _decode_element(text, str(kind))
                for text, kind in zip(texts, kinds, strict=True)
            ],
            index=decoded.index,
            dtype=object,
        )
        decoded = decoded.drop(columns=[kind_column])

    decoded = decoded.loc[:, [column for column in columns if column in decoded.columns]]
    # Arrow normalises some pandas dtypes on the way back (an all-null column
    # becomes typed null, a nullable int becomes float). Restore exactly what
    # the replay produced so no consumer sees a different dtype than it did
    # from the live path.
    for column, dtype in dtypes.items():
        if column in decoded.columns and str(decoded[column].dtype) != dtype:
            try:
                decoded[column] = decoded[column].astype(dtype)
            except (TypeError, ValueError):
                pass
    decoded.columns.name = meta.get("columns_name")
    return decoded


# ---------------------------------------------------------------------------
# source digest
# ---------------------------------------------------------------------------


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tracked_tree_files(tree: str, base: Path) -> list[str]:
    """Repo-relative files under ``tree`` that are COMMITTED, not merely present.

    A plain ``rglob`` walk makes the digest depend on whatever happens to be
    sitting in the working tree. A developer's untracked scratch output then
    produces a different digest from a clean clone, and the committed cache
    reads as stale in CI while looking fine locally - which is exactly what
    happened. Restricting to tracked files makes the input set identical in
    both places.
    """
    import subprocess

    try:
        result = subprocess.run(
            ["git", "ls-files", "-z", "--", tree],
            cwd=base,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        # No git (e.g. a source tarball): fall back to the on-disk walk and say
        # so in the manifest, so a mismatch is at least explainable.
        root = base / tree
        if not root.exists():
            return []
        return sorted(
            path.relative_to(base).as_posix()
            for path in root.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        )
    names = [name for name in result.stdout.decode("utf-8").split("\0") if name]
    return sorted(name for name in names if "__pycache__" not in name)


def _tree_entries(root: Path, base: Path) -> list[tuple[str, str]]:
    """Retained for callers that want a plain walk; not used by the digest."""
    if not root.exists():
        return []
    entries: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        entries.append((path.relative_to(base).as_posix(), _sha256_file(path)))
    return entries


def replay_source_file_hashes(repo_root: Path, engine: str) -> dict[str, str]:
    """Every committed non-pack replay input, path -> sha256."""
    engine = str(engine).strip().lower()
    hashes: dict[str, str] = {}
    for relative in (*_SOURCE_FILES, *_ENGINE_SOURCE_FILES.get(engine, ())):
        path = Path(repo_root) / relative
        hashes[relative] = _sha256_file(path) if path.exists() else "absent"
    for tree in _SOURCE_TREES:
        for relative in _tracked_tree_files(tree, Path(repo_root)):
            path = Path(repo_root) / relative
            hashes[relative] = _sha256_file(path) if path.exists() else "absent"
    return dict(sorted(hashes.items()))


def _hash_recorded_paths(repo_root: Path, recorded: dict[str, str]) -> dict[str, str]:
    """Re-hash exactly the paths the cache recorded, walking nothing."""
    current: dict[str, str] = {}
    for relative in sorted(recorded):
        path = Path(repo_root) / relative
        current[relative] = _sha256_file(path) if path.exists() else "absent"
    return current


# Packages whose source can change a replay result.  The concrete module list
# is not hard-coded: the builder records the repo-local modules the replay
# actually imported, and the runtime re-hashes exactly those.
_CODE_PACKAGES = ("model_dashboard", "pipeline")


def replay_calculation_code_modules(repo_root: Path) -> dict[str, str]:
    """Repo-local calculation modules currently loaded, path -> sha256.

    Captured from ``sys.modules`` after the replay has run, so the set comes
    from the real import graph rather than a hand-maintained list.  A module
    that is added later must be imported by one of these, whose own hash then
    changes, so the closure stays complete.
    """
    import sys

    modules: dict[str, str] = {}
    for name, module in list(sys.modules.items()):
        if not name.startswith(_CODE_PACKAGES):
            continue
        origin = getattr(module, "__file__", None)
        if not origin:
            continue
        path = Path(origin)
        try:
            relative = path.resolve().relative_to(Path(repo_root).resolve())
        except (ValueError, OSError):
            continue
        if path.exists():
            modules[relative.as_posix()] = _sha256_file(path)
    return dict(sorted(modules.items()))


def _hash_recorded_code_modules(repo_root: Path, recorded: dict[str, str]) -> dict[str, str]:
    """Re-hash exactly the modules the cache was built against."""
    return _hash_recorded_paths(repo_root, recorded)


def replay_cache_source_digest(
    pack_manifest: dict[str, Any],
    *,
    engine: str,
    bridge_vintage_id: str | None,
    repo_root: Path,
    code_module_hashes: dict[str, str] | None = None,
    source_file_hashes: dict[str, str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """(digest, provenance) over every value-relevant replay input.

    Covers the promoted pack content, the governed fitted state, the official
    vintage spines, the conflict/macro configuration, the builder/schema
    versions AND the calculation code itself.  Content hashes only - never
    mtimes - so a fresh clone and a working tree agree.

    Hashing the code matters as much as hashing the data: without it, editing
    ``fuel_price_scenario.py`` and forgetting to bump ``BUILDER_VERSION`` would
    leave a cache built by the OLD calculation still passing its digest, and
    the dashboard would serve superseded results indefinitely.
    """
    engine = str(engine).strip().lower()
    provenance: dict[str, Any] = {
        "schema_version": REPLAY_CACHE_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "engine": engine,
        "bridge_vintage_id": str(bridge_vintage_id or ""),
        "code_module_hashes": dict(code_module_hashes or {}),
        # The pack's own recorded per-file sha256 map: one value covering every
        # promoted table without re-hashing 67 MB on each load.
        "pack_output_hashes": pack_manifest.get("output_hashes", {}),
        "pack_schema_version": pack_manifest.get("schema_version", ""),
    }
    provenance["source_hashes"] = dict(
        source_file_hashes
        if source_file_hashes is not None
        else replay_source_file_hashes(repo_root, engine)
    )
    payload = json.dumps(provenance, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest(), provenance


# ---------------------------------------------------------------------------
# build / load
# ---------------------------------------------------------------------------


def replay_cache_dir(engine: str, repo_root: Path) -> Path:
    return Path(repo_root) / _CACHE_ROOT / str(engine).strip().lower()


def _walk_frames(obj: Any, prefix: str = "") -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for field in dataclasses.fields(obj):
        value = getattr(obj, field.name)
        name = f"{prefix}{field.name}"
        if isinstance(value, pd.DataFrame):
            frames[name] = value
        elif dataclasses.is_dataclass(value) and not isinstance(value, type):
            frames.update(_walk_frames(value, prefix=f"{name}."))
    return frames


def _scalar_fields(obj: Any, prefix: str = "") -> dict[str, Any]:
    scalars: dict[str, Any] = {}
    for field in dataclasses.fields(obj):
        value = getattr(obj, field.name)
        name = f"{prefix}{field.name}"
        if isinstance(value, pd.DataFrame):
            continue
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            scalars.update(_scalar_fields(value, prefix=f"{name}."))
        else:
            scalars[name] = list(value) if isinstance(value, tuple) else value
    return scalars


def _nested_result_class() -> type:
    """The only nested dataclass either replay result carries."""
    from model_dashboard.forecast_runner import ScenarioInputForecastReplayResult

    return ScenarioInputForecastReplayResult


def _rebuild(
    cls: type,
    frames: dict[str, pd.DataFrame],
    scalars: dict[str, Any],
    prefix: str = "",
) -> Any:
    """Invert ``_walk_frames``/``_scalar_fields`` for one dataclass."""
    kwargs: dict[str, Any] = {}
    for field in dataclasses.fields(cls):
        name = f"{prefix}{field.name}"
        if name in frames:
            kwargs[field.name] = frames[name]
        elif name in scalars:
            value = scalars[name]
            kwargs[field.name] = tuple(value) if isinstance(value, list) else value
        elif any(key.startswith(f"{name}.") for key in (*frames, *scalars)):
            kwargs[field.name] = _rebuild(
                _nested_result_class(), frames, scalars, prefix=f"{name}."
            )
        else:
            raise ReplayCacheError(
                f"Replay cache has no stored value for {cls.__name__}.{field.name}."
            )
    return cls(**kwargs)


def build_replay_cache(
    macro_result: Any,
    fuel_result: Any,
    *,
    engine: str,
    pack_manifest: dict[str, Any],
    bridge_vintage_id: str | None,
    repo_root: Path,
    source_main_sha: str = "",
) -> dict[str, Any]:
    """Write both replay results for one engine and return the manifest."""
    target = replay_cache_dir(engine, repo_root)
    frames_dir = target / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for stale in frames_dir.glob("*.parquet"):
        stale.unlink()

    # Captured AFTER the caller ran both replays, so sys.modules holds the real
    # calculation import graph rather than whatever the builder imported first.
    code_module_hashes = replay_calculation_code_modules(repo_root)
    # Committed inputs only: an untracked file in the builder's working tree
    # must not enter the digest, or the cache verifies here and reads as stale
    # on a clean clone.
    source_file_hashes = replay_source_file_hashes(repo_root, engine)
    digest, provenance = replay_cache_source_digest(
        pack_manifest,
        engine=engine,
        bridge_vintage_id=bridge_vintage_id,
        repo_root=repo_root,
        code_module_hashes=code_module_hashes,
        source_file_hashes=source_file_hashes,
    )

    frame_meta: dict[str, dict[str, Any]] = {}
    output_hashes: dict[str, str] = {}
    total_rows = 0
    for owner, result in (("macro", macro_result), ("fuel", fuel_result)):
        for name, frame in _walk_frames(result, prefix=f"{owner}.").items():
            encoded, meta = _encode_frame(frame)
            filename = f"{name}.parquet"
            path = frames_dir / filename
            # Deterministic bytes: no compression dictionary drift, no index.
            encoded.to_parquet(path, index=False, compression="zstd")
            meta["file"] = filename
            frame_meta[name] = meta
            output_hashes[filename] = _sha256_file(path)
            total_rows += int(len(frame))

    scalars: dict[str, Any] = {}
    for owner, result in (("macro", macro_result), ("fuel", fuel_result)):
        scalars.update(_scalar_fields(result, prefix=f"{owner}."))

    manifest = {
        "schema_version": REPLAY_CACHE_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "engine": str(engine).strip().lower(),
        "bridge_vintage_id": str(bridge_vintage_id or ""),
        "source_digest": digest,
        "source_main_sha": source_main_sha,
        "frames": frame_meta,
        "scalars": scalars,
        "output_hashes": output_hashes,
        "frame_count": len(frame_meta),
        "code_module_count": len(code_module_hashes),
        "row_count": total_rows,
        "bytes_on_disk": sum((frames_dir / name).stat().st_size for name in output_hashes),
        "provenance": provenance,
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    return manifest


def replay_cache_expected_digest(
    *,
    engine: str,
    pack_manifest: dict[str, Any],
    bridge_vintage_id: str | None,
    repo_root: Path,
) -> str:
    """The digest the committed cache SHOULD carry, given today's sources.

    Computed over the module list the cache recorded, so a caller that
    pre-computes this agrees exactly with ``replay_cache_status``. Falls back
    to the live import graph when no cache exists yet.
    """
    manifest_path = replay_cache_dir(engine, repo_root) / "manifest.json"
    recorded: dict[str, str] = {}
    if manifest_path.exists():
        try:
            recorded = dict(
                json.loads(manifest_path.read_text(encoding="utf-8"))
                .get("provenance", {})
                .get("code_module_hashes", {})
            )
        except (OSError, json.JSONDecodeError):
            recorded = {}
    recorded_sources: dict[str, str] = {}
    if manifest_path.exists():
        try:
            recorded_sources = dict(
                json.loads(manifest_path.read_text(encoding="utf-8"))
                .get("provenance", {})
                .get("source_hashes", {})
            )
        except (OSError, json.JSONDecodeError):
            recorded_sources = {}
    code_hashes = (
        _hash_recorded_paths(repo_root, recorded)
        if recorded
        else replay_calculation_code_modules(repo_root)
    )
    source_hashes = (
        _hash_recorded_paths(repo_root, recorded_sources)
        if recorded_sources
        else replay_source_file_hashes(repo_root, engine)
    )
    digest, _ = replay_cache_source_digest(
        pack_manifest,
        engine=engine,
        bridge_vintage_id=bridge_vintage_id,
        repo_root=repo_root,
        code_module_hashes=code_hashes,
        source_file_hashes=source_hashes,
    )
    return digest


def replay_cache_status(
    *,
    engine: str,
    pack_manifest: dict[str, Any],
    bridge_vintage_id: str | None,
    repo_root: Path,
    source_digest: str | None = None,
) -> tuple[str, str]:
    """('ok'|'missing'|'stale'|'corrupt', detail) without loading the frames.

    ``source_digest`` lets a caller that has already hashed the inputs skip
    doing it again: the scan covers ~48 MB across ~640 files and costs ~320 ms,
    which is worth paying once per process rather than once per check.
    """
    target = replay_cache_dir(engine, repo_root)
    manifest_path = target / "manifest.json"
    if not manifest_path.exists():
        return "missing", f"no compiled replay cache at {target.as_posix()}"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return "corrupt", f"unreadable manifest: {error}"
    if str(manifest.get("schema_version")) != REPLAY_CACHE_SCHEMA_VERSION:
        return "stale", (
            f"schema {manifest.get('schema_version')!r} != {REPLAY_CACHE_SCHEMA_VERSION!r}"
        )
    if source_digest is None:
        # Re-hash the paths the cache RECORDED - never a fresh tree walk, which
        # would make the digest depend on untracked working-tree files and let
        # a cache verify locally while reading as stale on a clean clone.
        # Doing it here rather than only inside the digest lets the message
        # name the file or module that moved.
        recorded_code = dict(manifest.get("provenance", {}).get("code_module_hashes", {}))
        if not recorded_code:
            return "stale", (
                "cache predates calculation-code hashing and cannot prove the "
                "replay logic is unchanged"
            )
        current_code = _hash_recorded_paths(repo_root, recorded_code)
        if current_code != recorded_code:
            changed = sorted(
                name for name, value in current_code.items() if recorded_code.get(name) != value
            )
            return "stale", (
                "replay calculation code changed: "
                + ", ".join(changed[:5])
                + (f" (+{len(changed) - 5} more)" if len(changed) > 5 else "")
            )
        recorded_sources = dict(manifest.get("provenance", {}).get("source_hashes", {}))
        current_sources = _hash_recorded_paths(repo_root, recorded_sources)
        if current_sources != recorded_sources:
            changed = sorted(
                name
                for name, value in current_sources.items()
                if recorded_sources.get(name) != value
            )
            return "stale", (
                "replay inputs changed: "
                + ", ".join(changed[:5])
                + (f" (+{len(changed) - 5} more)" if len(changed) > 5 else "")
            )
        source_digest, _ = replay_cache_source_digest(
            pack_manifest,
            engine=engine,
            bridge_vintage_id=bridge_vintage_id,
            repo_root=repo_root,
            code_module_hashes=current_code,
            source_file_hashes=current_sources,
        )
    digest = source_digest
    if str(manifest.get("source_digest")) != digest:
        return "stale", "replay inputs changed since the cache was built"
    return "ok", ""


def load_replay_cache(
    *,
    engine: str,
    pack_manifest: dict[str, Any],
    bridge_vintage_id: str | None,
    repo_root: Path,
    verify_hashes: bool = True,
    source_digest: str | None = None,
) -> tuple[Any, Any]:
    """Reconstruct (macro_result, fuel_result) exactly, or fail closed."""
    from model_dashboard.fuel_price_scenario import (
        DirectTreasuryScenarioReplayResult,
        FuelPriceScenarioReplayResult,
    )

    engine = str(engine).strip().lower()
    status, detail = replay_cache_status(
        engine=engine,
        pack_manifest=pack_manifest,
        bridge_vintage_id=bridge_vintage_id,
        repo_root=repo_root,
        source_digest=source_digest,
    )
    rebuild = _REBUILD_COMMAND.format(engine=engine)
    if status == "missing":
        raise ReplayCacheMissing(f"{detail}. Rebuild it with: {rebuild}")
    if status == "stale":
        raise ReplayCacheStale(
            f"Compiled Revenue Outlook replay cache for engine {engine!r} is stale ({detail}). "
            f"Rebuild it with: {rebuild}"
        )
    if status != "ok":
        raise ReplayCacheError(f"Replay cache for engine {engine!r} is unusable ({detail}). Rebuild: {rebuild}")

    target = replay_cache_dir(engine, repo_root)
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    frames_dir = target / "frames"

    frames: dict[str, pd.DataFrame] = {}
    for name, meta in manifest["frames"].items():
        path = frames_dir / str(meta["file"])
        if not path.exists():
            raise ReplayCacheError(
                f"Replay cache frame {name!r} is missing from {frames_dir.as_posix()}. Rebuild: {rebuild}"
            )
        if verify_hashes:
            expected = manifest["output_hashes"].get(str(meta["file"]))
            if expected and _sha256_file(path) != expected:
                raise ReplayCacheError(
                    f"Replay cache frame {name!r} failed hash validation. Rebuild: {rebuild}"
                )
        frames[name] = _decode_frame(pd.read_parquet(path), meta)

    scalars = dict(manifest.get("scalars", {}))
    macro = _rebuild(
        DirectTreasuryScenarioReplayResult,
        {k[len("macro.") :]: v for k, v in frames.items() if k.startswith("macro.")},
        {k[len("macro.") :]: v for k, v in scalars.items() if k.startswith("macro.")},
    )
    fuel = _rebuild(
        FuelPriceScenarioReplayResult,
        {k[len("fuel.") :]: v for k, v in frames.items() if k.startswith("fuel.")},
        {k[len("fuel.") :]: v for k, v in scalars.items() if k.startswith("fuel.")},
    )
    return macro, fuel

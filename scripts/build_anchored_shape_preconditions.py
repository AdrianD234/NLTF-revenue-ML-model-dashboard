"""Record the merged-main preconditions for the anchored structural shape work.

Section 0 of the brief: this runs BEFORE anything is modified and captures the
state the whole branch is measured against - the starting SHA, the governed
registry and its three role defaults, both runtime-pack manifest hashes, and
the existing UNBLENDED FY2031-FY2050 Current paths that the transition will be
compared to.

It is read-only against the repository. Everything it emits lands under
``artifacts/anchored_structural_shape_transition/`` and is committed as the
branch's starting evidence.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from model_dashboard.official_vintage import (  # noqa: E402
    load_official_vintage_registry,
    official_vintage_ids,
)
from model_dashboard.post_model_extrapolation import (  # noqa: E402
    FIRST_EXTRAPOLATION_FY,
    LAST_EXTRAPOLATION_FY,
    POST_MODEL_SEGMENT,
)

OUT = REPO_ROOT / "artifacts" / "anchored_structural_shape_transition"

# The PR #11 merge this branch must sit on top of.
REQUIRED_ANCESTOR_SHA = "82d2db67459226a9445fa50b7049c7cebc4032be"

PACK_DIRS = {
    "ensemble": Path("data") / "current_revenue_outlook",
    "ar1": Path("data") / "engine_ar1" / "current_revenue_outlook",
}


class PreconditionError(RuntimeError):
    """A documented precondition of the branch does not hold."""


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PreconditionError(message)


def check_git_state() -> dict[str, object]:
    """The branch must descend from the PR #11 merge on a clean tree."""

    head = _git("rev-parse", "HEAD")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    # Untracked additions are this branch's own new files and are recorded
    # rather than rejected. A MODIFIED tracked file is the real hazard: it
    # would mean the baseline is being read off something that is no longer
    # merged main.
    porcelain = [line for line in _git("status", "--porcelain").splitlines() if line.strip()]
    modified = [line for line in porcelain if not line.startswith("??")]
    untracked = [line[3:] for line in porcelain if line.startswith("??")]
    _require(
        not modified,
        "tracked files are modified; refusing to record a merged-main baseline over:\n"
        + "\n".join(modified),
    )
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", REQUIRED_ANCESTOR_SHA, "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    _require(
        ancestry.returncode == 0,
        f"HEAD does not descend from the PR #11 merge {REQUIRED_ANCESTOR_SHA}.",
    )
    return {
        "head_sha": head,
        "branch": branch,
        "required_ancestor_sha": REQUIRED_ANCESTOR_SHA,
        "descends_from_pr11_merge": True,
        "tracked_files_unmodified": True,
        "untracked_paths": sorted(untracked),
    }


def check_registry() -> dict[str, object]:
    """PR #11's two governed roles must still be intact and BEFU26-default."""

    registry = load_official_vintage_registry(REPO_ROOT)
    entries = {str(entry["vintage_id"]): entry for entry in registry["vintages"]}
    ids = list(official_vintage_ids(REPO_ROOT))
    _require("BEFU26" in entries, "BEFU26 is not registered.")
    _require("MBU26" in entries, "MBU26 is no longer registered.")

    def _single(flag: str) -> str:
        flagged = [vid for vid, entry in entries.items() if bool(entry.get(flag))]
        _require(len(flagged) == 1, f"expected exactly one vintage with {flag}, got {flagged}.")
        return flagged[0]

    latest = _single("is_latest")
    comparator = _single("is_default_comparator")
    bridge = _single("is_default_bridge_vintage")
    _require(latest == "BEFU26", f"latest vintage is {latest}, expected BEFU26.")
    _require(comparator == "BEFU26", f"default comparator is {comparator}, expected BEFU26.")
    _require(bridge == "BEFU26", f"default bridge vintage is {bridge}, expected BEFU26.")
    _require(
        bool(entries["MBU26"].get("available")),
        "MBU26 is registered but not available, so it is no longer selectable.",
    )
    return {
        "registry_schema_version": registry["schema_version"],
        "registered_vintage_ids": ids,
        "default_comparator_vintage_id": comparator,
        "default_bridge_vintage_id": bridge,
        "latest_vintage_id": latest,
        "mbu26_selectable": True,
        "roles_separately_governed": True,
    }


def check_packs() -> tuple[dict[str, object], pd.DataFrame]:
    """Both governed runtime packs must exist; record their manifest hashes."""

    summaries: dict[str, object] = {}
    hash_rows: list[dict[str, object]] = []
    for engine, relative in PACK_DIRS.items():
        base = REPO_ROOT / relative
        manifest_path = base / "manifest.json"
        _require(manifest_path.exists(), f"{engine}: {manifest_path} is missing.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        block = manifest.get("official_vintages") or {}
        _require(
            str(block.get("official_comparator_vintage_id")) == "BEFU26",
            f"{engine}: pack comparator vintage is not BEFU26.",
        )
        _require(
            str(block.get("bridge_assumption_vintage_id")) == "BEFU26",
            f"{engine}: pack bridge vintage is not BEFU26.",
        )
        _require(
            "long_run_shape_vintage_id" not in block,
            f"{engine}: pack already carries a long-run shape role; "
            "this recorder must run against unmodified merged main.",
        )
        summaries[engine] = {
            "pack_dir": relative.as_posix(),
            "manifest_sha256": sha256_of(manifest_path),
            "official_comparator_vintage_id": block.get("official_comparator_vintage_id"),
            "bridge_assumption_vintage_id": block.get("bridge_assumption_vintage_id"),
        }
        for artefact in sorted(base.rglob("*")):
            if artefact.is_file() and artefact.suffix in {".parquet", ".json", ".csv"}:
                hash_rows.append(
                    {
                        "engine": engine,
                        "path": artefact.relative_to(REPO_ROOT).as_posix(),
                        "sha256": sha256_of(artefact),
                        "size_bytes": artefact.stat().st_size,
                    }
                )
    return summaries, pd.DataFrame(hash_rows)


def unblended_long_run_paths() -> pd.DataFrame:
    """The existing FY2031-FY2050 Current rows, before any shape transition.

    Sourced from each committed pack's line reconciliation, filtered to the
    post-model segment. This is the ``unblended_current`` candidate and the
    thing every later candidate is measured against.
    """

    frames: list[pd.DataFrame] = []
    for engine, relative in PACK_DIRS.items():
        path = REPO_ROOT / relative / "revenue_line_reconciliation.parquet"
        _require(path.exists(), f"{engine}: {path} is missing.")
        frame = pd.read_parquet(path)
        fy = pd.to_numeric(frame["FY"], errors="coerce")
        scoped = frame[
            frame.get("forecast_segment", pd.Series("", index=frame.index))
            .astype(str)
            .eq(POST_MODEL_SEGMENT)
            & fy.between(FIRST_EXTRAPOLATION_FY, LAST_EXTRAPOLATION_FY)
        ].copy()
        _require(
            not scoped.empty,
            f"{engine}: no post-model FY{FIRST_EXTRAPOLATION_FY}-FY{LAST_EXTRAPOLATION_FY} "
            "rows found; the long-run layer precondition does not hold.",
        )
        scoped["engine"] = engine
        frames.append(
            scoped[
                [
                    "engine",
                    "source_path",
                    "series_id",
                    "FY",
                    "value",
                    "unit",
                    "formula",
                    "value_status",
                    "forecast_segment",
                ]
            ]
        )
    out = pd.concat(frames, ignore_index=True)
    return out.sort_values(["engine", "source_path", "series_id", "FY"]).reset_index(drop=True)


def check_supporting_preconditions() -> dict[str, object]:
    """Q1-2026 actuals, the exact-VFM composition source and the long-run layer."""

    vfm_path = REPO_ROOT / "data" / "vfm_202405" / "vfm_vkt_shares.csv"
    _require(vfm_path.exists(), "the exact VFM202405 share table is missing.")
    vfm = pd.read_csv(vfm_path)
    scenarios = sorted(vfm["scenario"].astype(str).unique())
    for required in ("Base_EV", "Fast_EV", "Slow_EV"):
        _require(required in scenarios, f"VFM scenario {required} is missing from {vfm_path.name}.")

    # The Q1-2026 refresh is recorded in the model-input history manifest and
    # carried in the per-stream input frames, not in the chart rows (whose
    # actuals are annual FY rows through FY2025).
    history_manifest = json.loads(
        (REPO_ROOT / "data" / "model_input_history" / "manifest.json").read_text(encoding="utf-8")
    )
    refreshes = history_manifest.get("refresh_history") or []
    q1_refresh = next(
        (entry for entry in refreshes if "2026Q1" in (entry.get("periods") or [])), None
    )
    _require(
        q1_refresh is not None,
        "the Q1-2026 actuals refresh is not recorded in the model-input history manifest.",
    )
    stream_latest: dict[str, str] = {}
    for stream in ("ped_inputs", "light_ruc_inputs", "heavy_ruc_inputs"):
        frame = pd.read_parquet(REPO_ROOT / "data" / "model_input_history" / f"{stream}.parquet")
        latest = max(frame["period"].astype(str))
        _require(
            latest == "2026Q1",
            f"{stream}: latest input period is {latest}, expected 2026Q1.",
        )
        stream_latest[stream] = latest
    _require(
        str(q1_refresh.get("ped_mode")) == "provisional_replay_only",
        "the 2026Q1 PED bridge is no longer provisional_replay_only; this branch "
        "must not reclassify it as an actual.",
    )

    return {
        "vfm_composition_source": vfm_path.relative_to(REPO_ROOT).as_posix(),
        "vfm_scenarios": scenarios,
        "vfm_source_sha256": sha256_of(vfm_path),
        "q1_2026_actuals_present": True,
        "q1_2026_ped_mode": q1_refresh.get("ped_mode"),
        "q1_2026_workbook_sha256": q1_refresh.get("workbook_sha256"),
        "stream_latest_input_period": stream_latest,
        "long_run_layer_first_fy": FIRST_EXTRAPOLATION_FY,
        "long_run_layer_last_fy": LAST_EXTRAPOLATION_FY,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    git_state = check_git_state()
    registry_state = check_registry()
    pack_state, pack_hashes = check_packs()
    supporting = check_supporting_preconditions()
    unblended = unblended_long_run_paths()

    unblended.to_csv(OUT / "preconditions_unblended_long_run_paths.csv", index=False)
    pack_hashes.to_csv(OUT / "preconditions_runtime_pack_hashes.csv", index=False)
    record = {
        "record_id": "anchored_structural_shape_transition_preconditions_v1",
        "git": git_state,
        "official_vintage_registry": registry_state,
        "runtime_packs": pack_state,
        "supporting": supporting,
        "unblended_long_run_rows": int(len(unblended)),
        "unblended_long_run_series": sorted(unblended["series_id"].astype(str).unique()),
        "unblended_long_run_source_paths": sorted(unblended["source_path"].astype(str).unique()),
    }
    (OUT / "preconditions_record.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

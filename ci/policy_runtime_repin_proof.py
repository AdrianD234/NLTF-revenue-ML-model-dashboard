"""Prove a policy-runtime repin moved provenance only, and no governed value.

A digest-bound source file changed (model_dashboard/data/chart_sources.py gained
an explicit output-root parameter with an unchanged default), so the committed
policy-runtime pack must stop claiming it was built from the old code. That is a
provenance repin, not a promotion.

The whole point of running it through this script is that "it should not change
any value" is a claim, and claims about governed numbers get checked. Snapshot
before, rebuild, compare every frame cell by cell, and refuse to proceed if any
decision-facing value moves.

Usage:
    python ci/policy_runtime_repin_proof.py --snapshot before.json
    python scripts/build_revenue_outlook_policy_runtime.py --all
    python ci/policy_runtime_repin_proof.py --compare before.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

import pandas as pd

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PACK_ROOT = REPO_ROOT / "data" / "revenue_outlook_policy_runtime"

# Manifest keys that are SUPPOSED to move in a repin: they identify the code the
# pack was built from. Anything else moving is a finding.
PROVENANCE_KEYS = {
    "source_digest",
    "source_main_sha",
    "provenance",
    "build_environment",
    "builder_version",
    "bytes_on_disk",
}


def frame_files() -> list[pathlib.Path]:
    if not PACK_ROOT.is_dir():
        return []
    return sorted(
        p for p in PACK_ROOT.rglob("*")
        if p.is_file() and p.suffix in {".parquet", ".csv"}
    )


def describe_frame(path: pathlib.Path) -> dict:
    """Structure plus a content digest that ignores file-format noise.

    Hashing the file alone would flag a parquet rewritten with different
    compression or row-group boundaries as a changed value, which it is not.
    The values digest is computed from the data itself.
    """
    try:
        frame = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
    except Exception as exc:
        return {"unreadable": f"{type(exc).__name__}: {exc}"}

    frame = frame.sort_index(axis=1)
    try:
        ordered = frame.sort_values(by=list(frame.columns), kind="stable").reset_index(drop=True)
    except Exception:
        ordered = frame.reset_index(drop=True)

    payload = ordered.to_csv(index=False).encode("utf-8")
    return {
        "rows": int(len(frame)),
        "columns": list(frame.columns),
        "dtypes": {c: str(t) for c, t in frame.dtypes.items()},
        "values_sha256": hashlib.sha256(payload).hexdigest(),
        "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def snapshot() -> dict:
    frames = {
        p.relative_to(REPO_ROOT).as_posix(): describe_frame(p) for p in frame_files()
    }
    manifests = {}
    for manifest_path in sorted(PACK_ROOT.rglob("manifest.json")):
        manifests[manifest_path.relative_to(REPO_ROOT).as_posix()] = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )
    return {"frames": frames, "manifests": manifests}


def compare(before: dict, after: dict) -> int:
    problems: list[str] = []
    notes: list[str] = []

    b_frames, a_frames = before["frames"], after["frames"]

    missing = sorted(set(b_frames) - set(a_frames))
    added = sorted(set(a_frames) - set(b_frames))
    if missing:
        problems.append(f"frames disappeared: {missing}")
    if added:
        problems.append(f"frames appeared: {added}")

    for key in sorted(set(b_frames) & set(a_frames)):
        b, a = b_frames[key], a_frames[key]
        if "unreadable" in b or "unreadable" in a:
            problems.append(f"{key}: unreadable ({b.get('unreadable') or a.get('unreadable')})")
            continue
        if b["rows"] != a["rows"]:
            problems.append(f"{key}: row count {b['rows']} -> {a['rows']}")
        if b["columns"] != a["columns"]:
            problems.append(f"{key}: columns changed")
        if b["dtypes"] != a["dtypes"]:
            changed = {c: (b["dtypes"].get(c), a["dtypes"].get(c))
                       for c in set(b["dtypes"]) | set(a["dtypes"])
                       if b["dtypes"].get(c) != a["dtypes"].get(c)}
            problems.append(f"{key}: dtypes changed {changed}")
        if b["values_sha256"] != a["values_sha256"]:
            problems.append(
                f"{key}: GOVERNED VALUES MOVED "
                f"({b['values_sha256'][:12]} -> {a['values_sha256'][:12]})"
            )
        elif b["file_sha256"] != a["file_sha256"]:
            notes.append(f"{key}: identical values, file bytes differ (encoding only)")

    for key in sorted(set(before["manifests"]) & set(after["manifests"])):
        b, a = before["manifests"][key], after["manifests"][key]
        moved = sorted(k for k in set(b) | set(a) if b.get(k) != a.get(k))
        unexpected = [k for k in moved if k not in PROVENANCE_KEYS]
        if unexpected:
            problems.append(f"{key}: non-provenance manifest keys moved: {unexpected}")
        expected = [k for k in moved if k in PROVENANCE_KEYS]
        if expected:
            notes.append(f"{key}: provenance repinned ({', '.join(expected)})")

    print("=" * 70)
    print("POLICY RUNTIME REPIN PROOF")
    print("=" * 70)
    print(f"frames compared : {len(set(b_frames) & set(a_frames))}")
    print(f"manifests       : {len(set(before['manifests']) & set(after['manifests']))}")
    print()

    if notes:
        print("Expected changes (provenance only):")
        for note in notes:
            print(f"  - {note}")
        print()

    if problems:
        print("PROBLEMS — a governed value or structure moved:")
        for problem in problems:
            print(f"  ! {problem}")
        print()
        print("Do NOT commit this repin. Report the frame, key and values above.")
        return 1

    print("No governed frame moved. Every value, row count, column and dtype is")
    print("identical; only provenance identifying the new code changed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--snapshot", type=pathlib.Path)
    group.add_argument("--compare", type=pathlib.Path)
    args = parser.parse_args(argv)

    if args.snapshot:
        data = snapshot()
        args.snapshot.parent.mkdir(parents=True, exist_ok=True)
        args.snapshot.write_text(json.dumps(data, indent=0, default=str), encoding="utf-8")
        print(f"snapshotted {len(data['frames'])} frame(s), "
              f"{len(data['manifests'])} manifest(s) -> {args.snapshot}")
        return 0

    before = json.loads(args.compare.read_text(encoding="utf-8"))
    return compare(before, snapshot())


if __name__ == "__main__":
    sys.exit(main())

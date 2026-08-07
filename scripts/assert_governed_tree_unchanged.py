"""Fail any test lane that modifies tracked or governed content.

This gate exists because of a real incident, recorded in
``artifacts/ci_optimisation/xdist_benchmark.md``: a parallel test run rewrote
``artifacts/chart_sources/r2_ladder_summary.csv`` and moved a governed PED
calibration R-squared from 0.559 to 0.580, while the sequential run left the
same file untouched. Nothing failed. No test complained. The only reason it was
caught at all was an incidental ``git status`` during a benchmark.

A test suite that can silently move a governed number is a suite whose green
result means less than it appears to. So every tier now snapshots the governed
tree before it runs and verifies it afterwards.

Two mechanisms, because neither alone is sufficient:

  * ``git status --porcelain`` / ``git diff --exit-code`` catch tracked files.
  * A SHA-256 map over ``data/**`` and every tracked path catches content that
    git ignores but the model depends on, and catches same-path rewrites that a
    porcelain summary can compress away.

Usage:
    python scripts/assert_governed_tree_unchanged.py --snapshot before.json
    ... run tests ...
    python scripts/assert_governed_tree_unchanged.py --verify before.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Paths a test lane is ALLOWED to write. Everything else is governed or tracked
# content and must not move. Kept deliberately short: each entry is a place we
# have decided results may legitimately land.
WRITABLE_PREFIXES = (
    "artifacts/ci_local/",
    "artifacts/ci_optimisation/",
    "artifacts/curated_data/",       # deterministically rebuilt before each run
    "artifacts/gdp_sign_guard_audit/",  # regenerated before each run by design
    "artifacts/ci_environment/",
    "test-output/",
    "build/",
    ".pytest_cache/",
    "__pycache__/",
)


def _is_writable(relative: str) -> bool:
    return any(relative.startswith(prefix) for prefix in WRITABLE_PREFIXES) or (
        "/__pycache__/" in relative or relative.endswith(".pyc")
    )


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def governed_paths(root: pathlib.Path) -> list[pathlib.Path]:
    """Every tracked file, plus every file under data/ whether tracked or not.

    data/ holds the governed packs. Much of it is gitignored, so a tracked-only
    view would miss precisely the content a stale-pack bug would move.
    """
    paths: set[pathlib.Path] = set()

    result = subprocess.run(
        ["git", "ls-files", "-z"],
        capture_output=True,
        text=True,
        cwd=root,
        check=False,
    )
    if result.returncode == 0:
        for entry in result.stdout.split("\0"):
            if entry:
                candidate = root / entry
                if candidate.is_file():
                    paths.add(candidate)

    data_dir = root / "data"
    if data_dir.is_dir():
        paths.update(p for p in data_dir.rglob("*") if p.is_file())

    return sorted(paths)


def snapshot(root: pathlib.Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in governed_paths(root):
        relative = path.relative_to(root).as_posix()
        if _is_writable(relative):
            continue
        try:
            hashes[relative] = _sha256(path)
        except OSError as exc:
            hashes[relative] = f"unreadable:{exc}"
    return hashes


def git_state(root: pathlib.Path) -> list[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        cwd=root,
        check=False,
    )
    return [
        line
        for line in result.stdout.splitlines()
        # Untracked new evidence under an allowed prefix is fine; a MODIFIED
        # tracked file never is.
        if line.strip() and not _is_writable(line[3:].strip())
    ]


def verify(root: pathlib.Path, before_path: pathlib.Path) -> int:
    payload = json.loads(before_path.read_text(encoding="utf-8"))
    # Snapshots are {"hashes": ..., "git": [...]}. Accept a bare hash map too,
    # so a snapshot taken by an older version still verifies.
    before = payload.get("hashes", payload)
    before_git = set(payload.get("git", [])) if isinstance(payload, dict) else set()

    after = snapshot(root)

    changed = sorted(k for k in before.keys() & after.keys() if before[k] != after[k])
    removed = sorted(before.keys() - after.keys())
    added = sorted(after.keys() - before.keys())

    # Only dirt this lane INTRODUCED counts. A branch that was already dirty
    # before the tests ran is the developer's business, not a test failure -
    # flagging it would make the gate cry wolf on every working branch and get
    # switched off, which is how gates die.
    tracked_dirty = [
        line
        for line in git_state(root)
        if line not in before_git and line.startswith((" M", "M ", "MM", " D", "D "))
    ]

    if not (changed or removed or tracked_dirty):
        print(f"Governed tree unchanged ({len(after)} files verified).")
        if added:
            print(f"  ({len(added)} new file(s) appeared outside the allowed scratch paths;")
            print("   listed below as informational, not a failure:)")
            for path in added[:20]:
                print(f"     + {path}")
        return 0

    print("", file=sys.stderr)
    print("GOVERNED TREE MUTATED BY THIS TEST LANE", file=sys.stderr)
    print("=" * 44, file=sys.stderr)
    print("", file=sys.stderr)
    print(
        "A test run must not change tracked or governed content. A lane that does\n"
        "can move a governed number without any test failing - see\n"
        "artifacts/ci_optimisation/xdist_benchmark.md for the incident this gate\n"
        "was written for.",
        file=sys.stderr,
    )
    print("", file=sys.stderr)

    if changed:
        print(f"CONTENT CHANGED ({len(changed)}):", file=sys.stderr)
        for path in changed:
            print(f"  M {path}", file=sys.stderr)
            print(f"      before {before[path][:16]}  after {after[path][:16]}", file=sys.stderr)
    if removed:
        print(f"REMOVED ({len(removed)}):", file=sys.stderr)
        for path in removed:
            print(f"  D {path}", file=sys.stderr)
    if tracked_dirty:
        print("GIT REPORTS DIRTY:", file=sys.stderr)
        for line in tracked_dirty:
            print(f"  {line}", file=sys.stderr)

    print("", file=sys.stderr)
    print(
        "Restore with: git checkout -- <paths>\n"
        "Then fix the test so it writes to a run-scoped directory instead.",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=pathlib.Path, default=REPO_ROOT)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--snapshot", type=pathlib.Path, help="write a hash map here")
    group.add_argument("--verify", type=pathlib.Path, help="compare against this hash map")
    args = parser.parse_args(argv)

    root = args.repo_root.resolve()

    if args.snapshot:
        hashes = snapshot(root)
        payload = {"hashes": hashes, "git": git_state(root)}
        args.snapshot.parent.mkdir(parents=True, exist_ok=True)
        args.snapshot.write_text(json.dumps(payload, indent=0), encoding="utf-8")
        print(f"Snapshotted {len(hashes)} governed file(s) -> {args.snapshot}")
        return 0

    return verify(root, args.verify)


if __name__ == "__main__":
    sys.exit(main())

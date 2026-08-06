"""Build the slim Databricks App runtime bundle.

Assembles ``build/databricks_app/app`` from the repository according to the
explicit policy in ``deployment/databricks_app_bundle_policy.json``: only the
runtime roots the deployed Streamlit app needs, with large audit CSVs replaced
by their governed Parquet twins and audit-only archives omitted. The output is
what the ``databricks-app`` branch publishes beneath ``app/`` so the Databricks
App source path never contains ``.git``, tests, docs or oversized files.

Usage:

    python scripts/build_databricks_app_bundle.py --source . \
        --output build/databricks_app/app --clean

The build fails closed rather than silently shipping a bundle that would be
rejected by (or misbehave on) Databricks Apps: any output file over the hard
10 MiB limit, a missing required file, a missing Parquet replacement, a
case-insensitive path collision, forbidden paths (.git / tests / docs /
deliverables) or an unclassified oversized source file aborts the build.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

MANIFEST_NAME = "databricks_app_bundle_manifest.json"
MANIFEST_SCHEMA_VERSION = 1
FORBIDDEN_BUNDLE_ROOTS = (".git", "tests", "docs", "deliverables")


class BundleBuildError(RuntimeError):
    """Raised when the bundle cannot be built exactly as the policy demands."""


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_policy(policy_path: Path) -> dict:
    if not policy_path.is_file():
        raise BundleBuildError(f"Bundle policy not found: {policy_path}")
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    if policy.get("schema_version") != 1:
        raise BundleBuildError(
            f"Unsupported bundle policy schema_version: {policy.get('schema_version')!r}"
        )
    required_keys = (
        "maximum_file_bytes",
        "warning_file_bytes",
        "required_root_files",
        "included_root_files",
        "included_roots",
        "excluded_roots",
        "excluded_dir_names",
        "omitted_files",
        "parquet_replacements",
        "external_volume_assets",
        "generated_files",
    )
    missing = [key for key in required_keys if key not in policy]
    if missing:
        raise BundleBuildError(f"Bundle policy is missing keys: {missing}")
    return policy


def git_head_sha(source: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise BundleBuildError(
            "Could not resolve the source commit SHA via git rev-parse: "
            + result.stderr.strip()
        )
    return result.stdout.strip()


def git_tracked_files(source: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(source), "ls-files", "-z"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise BundleBuildError("git ls-files failed in the source checkout")
    return [
        entry.decode("utf-8")
        for entry in result.stdout.split(b"\x00")
        if entry
    ]


def normalise(path: str) -> str:
    return str(PurePosixPath(path.replace("\\", "/")))


def is_under(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def matches_any(path: str, patterns: list[str]) -> bool:
    return any(
        is_under(path, pattern) or fnmatch.fnmatch(path, pattern)
        for pattern in patterns
    )


def select_files(policy: dict, tracked: list[str]) -> dict[str, dict]:
    """Map each bundle-relative path to its selection record.

    Selection is manifest-driven and explicit: a file enters the bundle only
    when it is a required/included root file or sits under an included root,
    and is not excluded, omitted, or a CSV superseded by a Parquet twin.
    """

    omitted = {normalise(entry["path"]): entry for entry in policy["omitted_files"]}
    replaced_csvs = {
        normalise(entry["csv"]): entry for entry in policy["parquet_replacements"]
    }
    external = {normalise(entry["path"]): entry for entry in policy["external_volume_assets"]}
    excluded_roots = [normalise(root) for root in policy["excluded_roots"]]
    excluded_dir_names = set(policy["excluded_dir_names"])

    included_roots: dict[str, dict] = {}
    for entry in policy["included_roots"]:
        included_roots[normalise(entry["path"])] = entry

    root_files: dict[str, dict] = {}
    for entry in policy["included_root_files"]:
        root_files[normalise(entry["path"])] = entry

    selected: dict[str, dict] = {}
    for raw in tracked:
        path = normalise(raw)
        parts = PurePosixPath(path).parts
        if any(part in excluded_dir_names for part in parts):
            continue
        if matches_any(path, excluded_roots):
            continue
        if path in omitted or path in external:
            continue
        if path in replaced_csvs:
            continue

        record = None
        if path in root_files:
            record = {
                "inclusion_reason": root_files[path].get("reason", "required root file"),
                "runtime_role": root_files[path].get("role", "runtime"),
            }
        else:
            for root, entry in included_roots.items():
                if is_under(path, root):
                    excludes = [normalise(p) for p in entry.get("exclude", [])]
                    if excludes and matches_any(path, excludes):
                        record = None
                        break
                    record = {
                        "inclusion_reason": entry.get(
                            "reason", f"under included runtime root {root}"
                        ),
                        "runtime_role": entry.get("role", "runtime"),
                    }
                    break
        if record is not None:
            selected[path] = record

    return selected


def enforce_replacements(policy: dict, selected: dict[str, dict]) -> None:
    for entry in policy["parquet_replacements"]:
        parquet = normalise(entry["parquet"])
        csv = normalise(entry["csv"])
        if parquet not in selected:
            raise BundleBuildError(
                f"Parquet replacement {parquet} (for {csv}) is not part of the "
                "selected bundle content; refusing to ship a bundle whose "
                "compact replacement is absent."
            )
        selected[parquet]["replacement_source"] = csv
        selected[parquet]["inclusion_reason"] = entry.get(
            "reason", f"compact Parquet replacement for {csv}"
        )


def enforce_required(policy: dict, selected: dict[str, dict]) -> None:
    generated = {normalise(entry["path"]) for entry in policy["generated_files"]}
    for required in policy["required_root_files"]:
        path = normalise(required)
        if path not in selected and path not in generated:
            raise BundleBuildError(f"Required bundle file is missing: {path}")


def enforce_forbidden(selected: dict[str, dict]) -> None:
    for path in selected:
        head = PurePosixPath(path).parts[0]
        if head in FORBIDDEN_BUNDLE_ROOTS:
            raise BundleBuildError(f"Forbidden path selected into the bundle: {path}")


def enforce_case_collisions(paths: list[str]) -> None:
    seen: dict[str, str] = {}
    for path in paths:
        key = path.lower()
        if key in seen and seen[key] != path:
            raise BundleBuildError(
                f"Case-insensitive path collision: {seen[key]} vs {path}"
            )
        seen[key] = path


def enforce_oversized_classified(
    policy: dict, source: Path, tracked: list[str], selected: dict[str, dict]
) -> list[dict]:
    """Every tracked source file over the hard limit must be classified."""

    maximum = int(policy["maximum_file_bytes"])
    omitted = {normalise(entry["path"]): entry for entry in policy["omitted_files"]}
    replaced = {normalise(entry["csv"]): entry for entry in policy["parquet_replacements"]}
    external = {normalise(entry["path"]): entry for entry in policy["external_volume_assets"]}

    oversized_report: list[dict] = []
    for raw in tracked:
        path = normalise(raw)
        file_path = source / path
        if not file_path.is_file():
            continue
        size = file_path.stat().st_size
        if size <= maximum:
            continue
        if path in replaced:
            reason = replaced[path].get("reason", "replaced by Parquet twin")
            action = "replace_with_parquet"
        elif path in omitted:
            reason = omitted[path].get("reason", "omitted from bundle")
            action = "omit"
        elif path in external:
            reason = external[path].get("reason", "served from Unity Catalog Volume")
            action = "externalise"
        elif path in selected:
            raise BundleBuildError(
                f"Oversized source file selected into the bundle: {path} ({size} bytes)"
            )
        else:
            raise BundleBuildError(
                f"Unclassified oversized source file: {path} ({size} bytes). "
                "Add it to omitted_files, parquet_replacements or "
                "external_volume_assets in the bundle policy."
            )
        oversized_report.append(
            {"path": path, "size_bytes": size, "action": action, "reason": reason}
        )
    return sorted(oversized_report, key=lambda entry: entry["path"])


def check_governed_manifests(source: Path, policy: dict, selected: dict[str, dict]) -> None:
    """Light fail-closed check: governed runtime manifests must parse and their
    Parquet-first runtime tables must be selected for the bundle."""

    for check in policy.get("governed_manifest_checks", []):
        manifest_rel = normalise(check["manifest"])
        manifest_path = source / manifest_rel
        if not manifest_path.is_file():
            raise BundleBuildError(f"Governed manifest missing: {manifest_rel}")
        try:
            json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise BundleBuildError(
                f"Governed manifest is invalid JSON: {manifest_rel}: {exc}"
            ) from exc
        if manifest_rel not in selected:
            raise BundleBuildError(
                f"Governed manifest is not selected into the bundle: {manifest_rel}"
            )
        for required_rel in check.get("required_runtime_files", []):
            required_path = normalise(required_rel)
            if required_path not in selected:
                raise BundleBuildError(
                    f"Runtime file required by {manifest_rel} is not selected: {required_path}"
                )


def copy_and_manifest(
    source: Path,
    output: Path,
    policy: dict,
    selected: dict[str, dict],
    source_sha: str,
    oversized_report: list[dict],
) -> dict:
    maximum = int(policy["maximum_file_bytes"])
    warning = int(policy["warning_file_bytes"])
    warning_exempt = {normalise(p) for p in policy.get("warning_exemptions", [])}

    files = []
    total_bytes = 0
    largest = {"path": None, "size_bytes": 0}
    for path in sorted(selected):
        src = source / path
        if not src.is_file():
            raise BundleBuildError(f"Selected file missing on disk: {path}")
        dest = output / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        size = dest.stat().st_size
        if size > maximum:
            raise BundleBuildError(
                f"Bundle file exceeds the 10 MiB Databricks limit: {path} ({size} bytes)"
            )
        if size > warning and path not in warning_exempt:
            raise BundleBuildError(
                f"Bundle file exceeds the 9 MiB warning threshold without an "
                f"explicit exemption: {path} ({size} bytes)"
            )
        record = selected[path]
        total_bytes += size
        if size > largest["size_bytes"]:
            largest = {"path": path, "size_bytes": size}
        files.append(
            {
                "path": path,
                "size_bytes": size,
                "sha256": sha256_of(dest),
                "source_path": path,
                "source_sha": source_sha,
                "inclusion_reason": record["inclusion_reason"],
                "runtime_role": record["runtime_role"],
                **(
                    {"replacement_source": record["replacement_source"]}
                    if "replacement_source" in record
                    else {}
                ),
            }
        )

    for entry in policy["generated_files"]:
        rel = normalise(entry["path"])
        template = source / normalise(entry["template"])
        if not template.is_file():
            raise BundleBuildError(f"Generated-file template missing: {entry['template']}")
        dest = output / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(template, dest)
        size = dest.stat().st_size
        total_bytes += size
        files.append(
            {
                "path": rel,
                "size_bytes": size,
                "sha256": sha256_of(dest),
                "source_path": normalise(entry["template"]),
                "source_sha": source_sha,
                "inclusion_reason": entry.get("reason", "generated deployment file"),
                "runtime_role": entry.get("role", "deployment"),
            }
        )

    files.sort(key=lambda record: record["path"])
    enforce_case_collisions([record["path"] for record in files] + [MANIFEST_NAME])

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "source_sha": source_sha,
        "policy_path": "deployment/databricks_app_bundle_policy.json",
        "maximum_file_bytes": maximum,
        "warning_file_bytes": warning,
        "file_count": len(files),
        "total_size_bytes": total_bytes,
        "largest_file": largest,
        "parquet_replacements": [
            {
                "csv": normalise(entry["csv"]),
                "parquet": normalise(entry["parquet"]),
                "reason": entry.get("reason", ""),
            }
            for entry in policy["parquet_replacements"]
        ],
        "excluded_oversized_files": oversized_report,
        "files": files,
    }
    manifest_path = output / MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    manifest["manifest_sha256"] = sha256_of(manifest_path)
    return manifest


def build(source: Path, output: Path, policy_path: Path, clean: bool) -> dict:
    policy = load_policy(policy_path)
    source_sha = git_head_sha(source)
    tracked = git_tracked_files(source)

    selected = select_files(policy, tracked)
    enforce_replacements(policy, selected)
    enforce_required(policy, selected)
    enforce_forbidden(selected)
    oversized_report = enforce_oversized_classified(policy, source, tracked, selected)
    check_governed_manifests(source, policy, selected)

    if clean and output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    manifest = copy_and_manifest(
        source, output, policy, selected, source_sha, oversized_report
    )

    stray = [
        str(path.relative_to(output))
        for path in output.rglob("*")
        if path.is_file()
    ]
    if len(stray) != manifest["file_count"] + 1:  # +1 for the manifest itself
        raise BundleBuildError(
            f"Bundle output contains {len(stray)} files but the manifest records "
            f"{manifest['file_count']} (+1 manifest). Re-run with --clean."
        )

    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", default=".", help="Repository checkout to bundle")
    parser.add_argument(
        "--output",
        default="build/databricks_app/app",
        help="Bundle output directory (created from scratch with --clean)",
    )
    parser.add_argument(
        "--policy",
        default="deployment/databricks_app_bundle_policy.json",
        help="Bundle policy JSON (relative to --source when not absolute)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete the output directory before building",
    )
    args = parser.parse_args(argv)

    source = Path(args.source).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = (source / output).resolve()
    policy_path = Path(args.policy)
    if not policy_path.is_absolute():
        policy_path = source / policy_path

    try:
        manifest = build(source, output, policy_path, clean=args.clean)
    except BundleBuildError as exc:
        print(f"BUNDLE BUILD FAILED: {exc}", file=sys.stderr)
        return 1

    print("Databricks App bundle built")
    print(f"  source sha        : {manifest['source_sha']}")
    print(f"  output            : {output}")
    print(f"  file count        : {manifest['file_count']} (+ manifest)")
    print(f"  total size        : {manifest['total_size_bytes'] / 1048576:.2f} MiB")
    print(
        "  largest file      : "
        f"{manifest['largest_file']['path']} "
        f"({manifest['largest_file']['size_bytes'] / 1048576:.2f} MiB)"
    )
    print(f"  parquet swaps     : {len(manifest['parquet_replacements'])}")
    print(f"  omitted oversized : {len(manifest['excluded_oversized_files'])}")
    print(f"  manifest sha256   : {manifest['manifest_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

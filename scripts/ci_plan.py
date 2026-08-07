"""Decide what a diff actually has to prove.

The old workflow ran one broad suite for every change, so a caption edit and a
promoted fitted state cost the same 74 hosted minutes. This planner classifies a
diff against ci/change_scopes.yml and emits only the test groups, pack checks
and hosted jobs that diff can genuinely invalidate.

Every unresolved case escalates. An unmatched file, an unmatched Python file, a
diff wider than the configured threshold, or any failure to classify at all
yields unknown_high_risk with full assurance and both replay platforms. The
planner can therefore be wrong about a *cheap* answer only by being expensive,
never by being silent.

Usage:
    python scripts/ci_plan.py --base origin/main --head HEAD --format human
    python scripts/ci_plan.py --event pull_request --format github-output
    python scripts/ci_plan.py --files a.py b.md --format json
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import pathlib
import subprocess
import sys

try:
    import yaml
except ImportError:  # pragma: no cover - surfaced as a clear message, not a stack
    print("ci_plan.py needs PyYAML (pip install pyyaml)", file=sys.stderr)
    raise

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = REPO_ROOT / "ci" / "change_scopes.yml"

RISK_ORDER = ["none", "low", "medium", "high"]


class PlannerError(RuntimeError):
    """Raised when the diff cannot be read at all."""


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def load_config(path: pathlib.Path = DEFAULT_CONFIG) -> dict:
    with path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    validate_config(config)
    return config


def validate_config(config: dict) -> None:
    """Fail loudly on a scope that references a group that no longer exists.

    A renamed test group would otherwise silently select nothing, which is the
    one failure mode this whole design exists to prevent.
    """
    groups = set(config["test_groups"])
    for scope_name, scope in config["scopes"].items():
        for group in scope.get("test_groups") or []:
            if group not in groups:
                raise PlannerError(
                    f"scope '{scope_name}' references unknown test group '{group}'"
                )
    for rule in config["rules"]:
        for scope in rule["scopes"]:
            if scope not in config["scopes"]:
                raise PlannerError(f"rule references unknown scope '{scope}'")


# ---------------------------------------------------------------------------
# Diff resolution
# ---------------------------------------------------------------------------


def changed_files(base: str, head: str, repo: pathlib.Path = REPO_ROOT) -> list[str]:
    """Files differing between base and head, using the merge base.

    ``git diff base...head`` compares head against the merge base, which is what
    a pull_request workflow tests. Comparing against the raw base tip would
    report unrelated files that simply landed on the base branch meanwhile.
    """
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        capture_output=True,
        text=True,
        cwd=repo,
        check=False,
    )
    if result.returncode != 0:
        # Fall back to a two-dot diff: shallow CI checkouts may lack the merge
        # base. Failing over is safe because a wider file list only escalates.
        result = subprocess.run(
            ["git", "diff", "--name-only", base, head],
            capture_output=True,
            text=True,
            cwd=repo,
            check=False,
        )
    if result.returncode != 0:
        raise PlannerError(
            f"could not diff {base}...{head}: {result.stderr.strip()}"
        )
    return sorted(line for line in result.stdout.splitlines() if line.strip())


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify_file(path: str, config: dict) -> list[str]:
    """Every scope whose rules match this path. Empty means unclassified."""
    matched: list[str] = []
    for rule in config["rules"]:
        for pattern in rule["patterns"]:
            if path_matches(path, pattern):
                for scope in rule["scopes"]:
                    if scope not in matched:
                        matched.append(scope)
                break
    return matched


def path_matches(path: str, pattern: str) -> bool:
    """Glob match with ``**`` meaning "this directory and everything under it"."""
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return path == prefix or path.startswith(prefix + "/")
    return fnmatch.fnmatchcase(path, pattern)


def plan(
    files: list[str],
    config: dict,
    event: str = "local",
    repo: pathlib.Path = REPO_ROOT,
) -> dict:
    failsafe = config.get("failsafe", {})
    scopes: list[str] = []
    reasons: list[str] = []
    unclassified: list[str] = []
    file_scopes: dict[str, list[str]] = {}

    for path in files:
        matched = classify_file(path, config)
        file_scopes[path] = matched
        if not matched:
            unclassified.append(path)
            continue
        for scope in matched:
            if scope not in scopes:
                scopes.append(scope)

    # --- fail-safe escalation ------------------------------------------------
    if unclassified:
        python_like = [p for p in unclassified if p.endswith((".py", ".pyi"))]
        data_like = [p for p in unclassified if p.startswith("data/")]
        scopes.append("unknown_high_risk")
        if python_like:
            reasons.append(
                f"{len(python_like)} unclassified Python file(s) escalate to high risk: "
                + ", ".join(sorted(python_like)[:5])
            )
        if data_like:
            reasons.append(
                f"{len(data_like)} unclassified data file(s) escalate to high risk: "
                + ", ".join(sorted(data_like)[:5])
            )
        other = [p for p in unclassified if p not in python_like and p not in data_like]
        if other:
            reasons.append(
                f"{len(other)} unclassified file(s) escalate to high risk: "
                + ", ".join(sorted(other)[:5])
            )

    threshold = failsafe.get("large_diff_file_threshold", 120)
    if len(files) > threshold:
        if "unknown_high_risk" not in scopes:
            scopes.append("unknown_high_risk")
        reasons.append(
            f"diff touches {len(files)} files (> {threshold}); not worth classifying, "
            "running full assurance"
        )

    if not files:
        reasons.append("no files changed against the base")

    # docs_only only survives when it is the *only* scope. One source file in
    # the diff and the cheap lane is gone.
    real_scopes = [s for s in scopes if s != "docs_only"]
    if "docs_only" in scopes and real_scopes:
        scopes = real_scopes
        reasons.append(
            "documentation changed alongside source; the docs-only lane does not apply"
        )

    # --- aggregate requirements ---------------------------------------------
    definitions = config["scopes"]
    test_groups: list[str] = []
    pack_checks: list[str] = []
    requires_full = False
    requires_linux_replay = False
    requires_windows_replay = False
    requires_browser = False
    requires_bundle = False
    risk = "none"

    for scope in scopes:
        definition = definitions[scope]
        for group in definition.get("test_groups") or []:
            if group not in test_groups:
                test_groups.append(group)
        for check in definition.get("pack_status_checks") or []:
            if check not in pack_checks:
                pack_checks.append(check)
        requires_full |= bool(definition.get("requires_full_assurance"))
        requires_linux_replay |= bool(definition.get("requires_linux_replay"))
        requires_windows_replay |= bool(definition.get("requires_windows_replay"))
        requires_browser |= bool(definition.get("requires_browser"))
        requires_bundle |= bool(definition.get("requires_databricks_bundle"))
        if RISK_ORDER.index(definition.get("risk", "none")) > RISK_ORDER.index(risk):
            risk = definition.get("risk", "none")
        reasons.append(f"{scope}: {definition['description']}")

    # Full assurance subsumes every group, so listing them individually would
    # only invite a stale list to disagree with the suite that actually runs.
    if requires_full:
        reasons.append(
            "full assurance selected: the complete not-e2e suite runs, so per-group "
            "selection is advisory only"
        )

    # A changed test file always runs itself, whatever its subject matter is.
    changed_tests = [
        p for p in files if p.startswith("tests/") and pathlib.PurePosixPath(p).name.startswith("test_")
    ]

    node_ids = resolve_test_paths(test_groups, config, repo)
    node_ids.extend(p for p in changed_tests if p not in node_ids)

    return {
        "event": event,
        "changed_files": files,
        "file_scopes": file_scopes,
        "unclassified_files": unclassified,
        "scopes": scopes,
        "risk_level": risk,
        "required_test_groups": test_groups,
        "required_test_paths": sorted(set(node_ids)),
        "required_pack_status_checks": pack_checks,
        "required_pack_rebuilds": [],  # owned by plan_governed_pack_rebuilds.py
        "requires_full_assurance": requires_full,
        "requires_linux_replay": requires_linux_replay,
        "requires_windows_replay": requires_windows_replay,
        "requires_browser": requires_browser,
        "requires_databricks_bundle": requires_bundle,
        "reasons": reasons,
    }


def resolve_test_paths(
    groups: list[str], config: dict, repo: pathlib.Path
) -> list[str]:
    """Expand group names to test paths, dropping any that no longer exist.

    A vanished path is reported by the planner tests rather than tolerated here,
    but selection itself must not hand pytest an argument that fails collection.
    """
    paths: list[str] = []
    for group in groups:
        for path in config["test_groups"][group]["paths"]:
            if path not in paths and (repo / path).exists():
                paths.append(path)
    return paths


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def render_human(result: dict) -> str:
    lines = [
        "CI plan",
        "=======",
        f"event            : {result['event']}",
        f"changed files    : {len(result['changed_files'])}",
        f"risk level       : {result['risk_level']}",
        f"scopes           : {', '.join(result['scopes']) or '(none)'}",
        "",
        "Required hosted work",
        "--------------------",
        f"  full assurance   : {yesno(result['requires_full_assurance'])}",
        f"  linux replay     : {yesno(result['requires_linux_replay'])}",
        f"  windows replay   : {yesno(result['requires_windows_replay'])}",
        f"  browser          : {yesno(result['requires_browser'])}",
        f"  databricks bundle: {yesno(result['requires_databricks_bundle'])}",
        "",
        f"Test groups ({len(result['required_test_groups'])})",
        "-----------",
    ]
    lines.extend(f"  - {g}" for g in result["required_test_groups"] or ["(none)"])
    lines += ["", f"Test paths ({len(result['required_test_paths'])})", "-----------"]
    lines.extend(f"  {p}" for p in result["required_test_paths"] or ["(none)"])
    lines += ["", "Pack status checks", "------------------"]
    lines.extend(
        f"  - {c}" for c in result["required_pack_status_checks"] or ["(none)"]
    )
    lines += ["", "Reasons", "-------"]
    lines.extend(f"  * {r}" for r in result["reasons"] or ["(none)"])
    if result["unclassified_files"]:
        lines += ["", "UNCLASSIFIED (escalated)", "------------------------"]
        lines.extend(f"  ! {p}" for p in result["unclassified_files"])
    return "\n".join(lines)


def yesno(value: bool) -> str:
    return "yes" if value else "no"


def render_github_output(result: dict) -> str:
    """Emit GITHUB_OUTPUT key=value lines for the conditional jobs to read."""
    booleans = {
        "requires_full_assurance": result["requires_full_assurance"],
        "requires_linux_replay": result["requires_linux_replay"],
        "requires_windows_replay": result["requires_windows_replay"],
        "requires_browser": result["requires_browser"],
        "requires_databricks_bundle": result["requires_databricks_bundle"],
    }
    lines = [f"{key}={'true' if value else 'false'}" for key, value in booleans.items()]
    lines.append(f"risk_level={result['risk_level']}")
    lines.append(f"scopes={','.join(result['scopes'])}")
    lines.append(f"test_paths={' '.join(result['required_test_paths'])}")
    lines.append(f"pack_checks={','.join(result['required_pack_status_checks'])}")
    lines.append(f"changed_file_count={len(result['changed_files'])}")
    # The plan is echoed as one JSON blob so the summary job can render the same
    # decision the conditional jobs branched on.
    lines.append(f"plan_json={json.dumps(result, separators=(',', ':'))}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main", help="base git ref")
    parser.add_argument("--head", default="HEAD", help="head git ref")
    parser.add_argument(
        "--event",
        default="local",
        choices=["pull_request", "push", "local"],
        help="what triggered this plan",
    )
    parser.add_argument(
        "--format", default="human", choices=["json", "github-output", "human"]
    )
    parser.add_argument(
        "--files",
        nargs="*",
        help="classify this explicit file list instead of diffing git",
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args(argv)

    config = load_config(pathlib.Path(args.config))

    if args.files is not None:
        files = sorted(args.files)
    else:
        try:
            files = changed_files(args.base, args.head)
        except PlannerError as exc:
            # Classification failed outright. Do not guess: demand everything.
            result = {
                "event": args.event,
                "changed_files": [],
                "file_scopes": {},
                "unclassified_files": [],
                "scopes": ["unknown_high_risk"],
                "risk_level": "high",
                "required_test_groups": [],
                "required_test_paths": [],
                "required_pack_status_checks": [],
                "required_pack_rebuilds": [],
                "requires_full_assurance": True,
                "requires_linux_replay": True,
                "requires_windows_replay": True,
                "requires_browser": False,
                "requires_databricks_bundle": False,
                "reasons": [f"classifier failed, escalating to full assurance: {exc}"],
            }
            emit(result, args.format)
            return 0

    result = plan(files, config, event=args.event)
    emit(result, args.format)
    return 0


def emit(result: dict, fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(result, indent=2))
    elif fmt == "github-output":
        text = render_github_output(result)
        print(text)
        target = os.environ.get("GITHUB_OUTPUT")
        if target:
            with open(target, "a", encoding="utf-8") as handle:
                handle.write(text + "\n")
    else:
        print(render_human(result))


if __name__ == "__main__":
    sys.exit(main())

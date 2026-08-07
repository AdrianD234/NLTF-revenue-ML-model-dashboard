"""Report which governed packs are actually stale, and in what order to fix them.

Rebuilding every pack because a nearby file changed is expensive and, worse,
hides the question of whether anything needed rebuilding at all. This script
answers that question from the packs' own committed digests rather than from a
guess about the diff.

It deliberately reuses the existing status functions instead of recomputing
digests:

    replay_cache        model_dashboard.revenue_outlook_replay_cache.replay_cache_status
    quarterly_display   model_dashboard.revenue_outlook_series_coverage
                            .quarterly_display_pack_source_digest
    uncertainty         manifest source_files hashes
    policy_runtime      model_dashboard.revenue_outlook_policy_runtime
                            .policy_runtime_status
    databricks_bundle   derived: stale whenever anything upstream of it is

Reimplementing those digests here would create a second opinion about whether a
pack is fresh, and the two would eventually disagree. There must be exactly one
authority, and it is the runtime's own gate.

This script NEVER rebuilds anything. It prints what to run and why. Pack
building belongs in the local promotion workflow where the result can be
inspected before it is committed.

Usage:
    python scripts/plan_governed_pack_rebuilds.py
    python scripts/plan_governed_pack_rebuilds.py --format json
    python scripts/plan_governed_pack_rebuilds.py --fail-on-stale
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ENGINES = ("ar1", "ensemble")

# Rebuild order is a real dependency chain, not a preference. Each pack's digest
# chains the one above it, so rebuilding out of order produces a pack that is
# immediately stale against its own upstream.
REBUILD_ORDER = [
    "replay_cache",
    "quarterly_display",
    "uncertainty",
    "policy_runtime",
    "databricks_bundle",
]

REBUILD_COMMANDS = {
    "replay_cache": "python scripts/build_revenue_outlook_replay_cache.py --all",
    "quarterly_display": "python scripts/build_revenue_outlook_quarterly_display_pack.py",
    "uncertainty": "python scripts/build_revenue_outlook_uncertainty_pack.py",
    "policy_runtime": "python scripts/build_revenue_outlook_policy_runtime.py --all",
    "databricks_bundle": (
        "python scripts/build_databricks_app_bundle.py "
        "--source . --output build/databricks_app/app --clean"
    ),
}


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: pathlib.Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        return {"__corrupt__": str(exc)}


# ---------------------------------------------------------------------------
# Per-pack status
# ---------------------------------------------------------------------------


def status_replay_cache(root: pathlib.Path) -> dict:
    from model_dashboard.official_vintage import bridge_vintage_id_from_manifest
    from model_dashboard.revenue_outlook_policy_runtime import upstream_manifests
    from model_dashboard.revenue_outlook_replay_cache import replay_cache_status

    per_engine = {}
    worst = "ok"
    details = []
    for engine in ENGINES:
        pack_manifest, _replay, _unc = upstream_manifests(engine, root)
        status, detail = replay_cache_status(
            engine=engine,
            pack_manifest=pack_manifest,
            bridge_vintage_id=bridge_vintage_id_from_manifest(pack_manifest, root),
            repo_root=root,
        )
        per_engine[engine] = status
        if status != "ok":
            details.append(f"{engine}: {detail}")
            worst = _worse(worst, status)
    return {"status": worst, "detail": "; ".join(details) or "all engines ok",
            "per_engine": per_engine}


def status_quarterly_display(root: pathlib.Path) -> dict:
    from model_dashboard.revenue_outlook_series_coverage import (
        quarterly_display_pack_source_digest,
    )

    manifest_path = root / "data" / "revenue_outlook_quarterly_display" / "manifest.json"
    manifest = _read_json(manifest_path)
    if not manifest:
        return {"status": "missing", "detail": f"{manifest_path} is absent"}
    if "__corrupt__" in manifest:
        return {"status": "corrupt", "detail": manifest["__corrupt__"]}

    expected = quarterly_display_pack_source_digest(root)
    recorded = str(manifest.get("source_digest", ""))
    if not recorded:
        return {"status": "corrupt", "detail": "manifest records no source_digest"}
    if recorded != expected:
        return {
            "status": "stale",
            "detail": f"source digest {recorded[:12]} != expected {expected[:12]}",
        }
    return {"status": "ok", "detail": f"source digest {recorded[:12]}"}


def status_uncertainty(root: pathlib.Path) -> dict:
    """Presence and integrity only. Freshness is decided by the policy runtime.

    The uncertainty manifest has no independent source digest. Its
    ``source_files`` entries are provenance PROSE, not a hash map - for example
    ``"data/current_revenue_outlook (line reconciliation, current_basecase)"`` -
    so they cannot decide staleness, and an early version of this script that
    treated them as paths reported the pack stale on a clean tree.

    Rather than invent a second opinion, freshness is left to the authority that
    already owns it: ``policy_runtime_source_digest`` chains this manifest's
    ``scenario_key_digest``, ``seed`` and ``draws``, so a regenerated
    uncertainty pack makes the policy runtime stale, and that is what gets
    reported. Two independent staleness rules would eventually disagree, and the
    disagreement would be silent.
    """
    manifest_path = root / "data" / "revenue_outlook_uncertainty" / "manifest.json"
    manifest = _read_json(manifest_path)
    if not manifest:
        return {"status": "missing", "detail": f"{manifest_path} is absent"}
    if "__corrupt__" in manifest:
        return {"status": "corrupt", "detail": manifest["__corrupt__"]}

    digest = str(manifest.get("scenario_key_digest", ""))
    if not digest:
        return {
            "status": "corrupt",
            "detail": "manifest records no scenario_key_digest, so the policy "
            "runtime cannot chain it",
        }

    rows = manifest.get("band_rows", "?")
    return {
        "status": "ok",
        "detail": (
            f"present, scenario_key_digest {digest[:12]}, {rows} band rows; "
            "freshness is enforced transitively via policy_runtime"
        ),
    }


def status_policy_runtime(root: pathlib.Path) -> dict:
    from model_dashboard.revenue_outlook_policy_runtime import policy_runtime_status

    per_engine = {}
    worst = "ok"
    details = []
    for engine in ENGINES:
        status, detail = policy_runtime_status(engine=engine, repo_root=root)
        per_engine[engine] = status
        if status != "ok":
            details.append(f"{engine}: {detail}")
            worst = _worse(worst, status)
    return {"status": worst, "detail": "; ".join(details) or "all engines ok",
            "per_engine": per_engine}


def status_databricks_bundle(root: pathlib.Path, upstream: dict) -> dict:
    """The bundle is a projection of main, so it is stale when main's packs are.

    It carries no independent digest of its own upstream, and rebuilding it
    against stale packs would publish stale content with a fresh manifest -
    the one failure this ordering exists to prevent.
    """
    blocking = [
        name
        for name in ("replay_cache", "quarterly_display", "uncertainty", "policy_runtime")
        if upstream.get(name, {}).get("status") not in (None, "ok")
    ]
    if blocking:
        return {
            "status": "affected",
            "detail": "upstream pack(s) not ok: " + ", ".join(blocking),
        }
    return {
        "status": "not affected",
        "detail": "every upstream pack is ok; the bundle is republished on merge to main",
    }


_SEVERITY = {"ok": 0, "not affected": 0, "affected": 1, "stale": 2, "missing": 3, "corrupt": 4}


def _worse(left: str, right: str) -> str:
    return left if _SEVERITY.get(left, 9) >= _SEVERITY.get(right, 9) else right


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------


def build_plan(root: pathlib.Path) -> dict:
    packs: dict[str, dict] = {}

    for name, fn in (
        ("replay_cache", status_replay_cache),
        ("quarterly_display", status_quarterly_display),
        ("uncertainty", status_uncertainty),
        ("policy_runtime", status_policy_runtime),
    ):
        try:
            packs[name] = fn(root)
        except Exception as exc:  # a status check that cannot run is not "ok"
            packs[name] = {
                "status": "corrupt",
                "detail": f"status check raised {type(exc).__name__}: {exc}",
            }

    packs["databricks_bundle"] = status_databricks_bundle(root, packs)

    needs_rebuild = [
        name
        for name in REBUILD_ORDER
        if packs[name]["status"] in ("stale", "missing", "corrupt", "affected")
    ]

    # A pack downstream of a rebuilt one must be rebuilt too: its digest chains
    # the upstream manifest, so leaving it alone would leave it stale.
    if needs_rebuild:
        first = min(REBUILD_ORDER.index(n) for n in needs_rebuild)
        cascade = REBUILD_ORDER[first:]
        for name in cascade:
            if name not in needs_rebuild:
                packs[name]["detail"] += (
                    " (currently ok, but rebuilt anyway: its digest chains an "
                    "upstream pack that is being rebuilt)"
                )
        needs_rebuild = cascade

    for name, record in packs.items():
        record["rebuild_command"] = REBUILD_COMMANDS[name]
        record["required"] = name in needs_rebuild
        record["order"] = REBUILD_ORDER.index(name) + 1 if name in needs_rebuild else None

    return {
        "repo_root": str(root),
        "packs": packs,
        "required_rebuilds": needs_rebuild,
        "rebuild_commands": [REBUILD_COMMANDS[n] for n in needs_rebuild],
        "any_stale": bool(needs_rebuild),
        # A second identical build proves nothing unless determinism is in doubt.
        "second_idempotency_build_required": False,
        "second_build_reason": (
            "Not required. Run one only when the builder code or schema changed, "
            "output determinism is in doubt, or release assurance asks for it."
        ),
    }


def render_human(plan: dict) -> str:
    lines = ["Governed pack status", "====================", ""]
    width = max(len(n) for n in plan["packs"])
    for name in REBUILD_ORDER:
        record = plan["packs"][name]
        flag = "REBUILD" if record["required"] else "       "
        lines.append(f"  {flag}  {name:<{width}}  {record['status']:<12}  {record['detail']}")
    lines.append("")
    if plan["required_rebuilds"]:
        lines.append("Rebuild in this order:")
        for index, name in enumerate(plan["required_rebuilds"], start=1):
            lines.append(f"  {index}. {name}")
            lines.append(f"       {REBUILD_COMMANDS[name]}")
        lines.append("")
        lines.append(f"Second idempotency build: {plan['second_build_reason']}")
    else:
        lines.append("Every governed pack is current. Nothing to rebuild.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=pathlib.Path, default=REPO_ROOT)
    parser.add_argument("--format", default="human", choices=["human", "json"])
    parser.add_argument(
        "--fail-on-stale",
        action="store_true",
        help="exit non-zero when any pack needs rebuilding (for CI status checks)",
    )
    parser.add_argument(
        "--only",
        default="",
        help=(
            "comma-separated pack names to gate on. The full status is still "
            "reported; only these decide the exit code. Used by the affected "
            "tier, which gates on the packs its change plan actually requested."
        ),
    )
    args = parser.parse_args(argv)

    plan = build_plan(args.repo_root.resolve())

    # A stale pack only matters to a lane whose selected tests load it. A
    # dashboard UI change marks the policy runtime stale - ui.py is digest-bound
    # - but the tests that change selects never load a policy state, and they
    # pass. Failing them would make the cheapest, most common lane the one that
    # demands a pack rebuild, which is precisely backwards.
    gated = [p.strip() for p in args.only.split(",") if p.strip()]
    if gated:
        unknown = [p for p in gated if p not in plan["packs"]]
        if unknown:
            print(f"unknown pack name(s) in --only: {unknown}", file=sys.stderr)
            return 2
        blocking = [p for p in plan["required_rebuilds"] if p in gated]
        plan = dict(plan)
        plan["gated_on"] = gated
        plan["any_stale"] = bool(blocking)

    if args.format == "json":
        print(json.dumps(plan, indent=2))
    else:
        print(render_human(plan))

    if args.fail_on_stale and plan["any_stale"]:
        print(
            "\nFAIL: committed governed packs are stale. Rebuild them locally with the "
            "commands above and commit the result; CI validates pack status, it does "
            "not rebuild packs.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

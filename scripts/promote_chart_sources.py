"""Publish governed chart-source evidence, explicitly and on purpose.

Loading an evidence pack no longer writes these tables as a side effect, so this
is the only supported way to refresh ``artifacts/chart_sources``. Normal
application startup is read-only (issue #31).

Two engine identities produce two different, individually valid PED calibration
R-squared values. The committed tables carry the ``ensemble`` identity, so that
is the default and the only identity this command will publish into the
canonical filenames without an explicit override. AR(1) output goes to an
engine-keyed diagnostic directory instead, because two identities must never
share one canonical filename.

Examples::

    # Refresh the governed tables from the ensemble evidence pack.
    python scripts/promote_chart_sources.py

    # Generate AR(1) diagnostics without touching governed evidence.
    python scripts/promote_chart_sources.py --engine ar1

    # See what would change, writing nothing.
    python scripts/promote_chart_sources.py --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PYARROW24 = ROOT / ".runtime_pyarrow24"
if RUNTIME_PYARROW24.exists() and str(RUNTIME_PYARROW24) not in sys.path:
    sys.path.insert(0, str(RUNTIME_PYARROW24))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_dashboard.data.chart_sources import (  # noqa: E402
    CANONICAL_CHART_SOURCE_ENGINE,
    CHART_SOURCE_FILES,
    CHART_SOURCE_WRITE_PROMOTE,
    CHART_SOURCE_WRITE_SCRATCH,
    CORE_COLUMNS,
    canonical_chart_source_dir,
    engine_diagnostic_chart_source_dir,
    write_chart_source_tables,
)
from model_dashboard.evidence_pack import load_evidence_pack  # noqa: E402

ENGINE_AR1 = "ar1"
ENGINES = (CANONICAL_CHART_SOURCE_ENGINE, ENGINE_AR1)

# The governed tables. These three are the tracked ones; the rest of
# CHART_SOURCE_FILES is generated but gitignored.
GOVERNED_FILES = (
    "r2_ladder_summary.csv",
    "r2_reproducibility_gap_register.csv",
    "r2_training_fit_detail.csv",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--engine",
        choices=ENGINES,
        default=CANONICAL_CHART_SOURCE_ENGINE,
        help=f"Engine identity to publish (default: {CANONICAL_CHART_SOURCE_ENGINE}, the governed identity).",
    )
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--data-root", default=None, help="Override the evidence pack root for the chosen engine.")
    parser.add_argument("--output", default=None, help="Write here instead of the engine's default destination.")
    parser.add_argument(
        "--allow-noncanonical-engine",
        action="store_true",
        help="Deliberately publish a non-governed engine identity into the canonical filenames.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without writing.")
    parser.add_argument("--json-out", default=None)
    return parser.parse_args(argv)


def evidence_pack_root(repo_root: Path, engine: str) -> Path:
    if engine == ENGINE_AR1:
        return repo_root / "data" / "engine_ar1" / "dashboard_evidence_pack"
    return repo_root / "data" / "dashboard_evidence_pack"


def ped_calibration_r2(chart_dir: Path) -> dict[str, str]:
    """The PED calibration R-squared pair, keyed by score basis."""
    path = chart_dir / "r2_ladder_summary.csv"
    if not path.exists():
        return {}
    found: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("chart_id") != "r2_ladder_summary":
                continue
            if row.get("stream_label") != "PED VKT per capita":
                continue
            basis = (row.get("score_basis") or "").strip()
            value = (row.get("calibration_r2") or "").strip()
            if basis and value:
                found[basis] = value
    return found


def validate_output(output_dir: Path) -> list[str]:
    """Every expected table present, non-empty, correctly shaped, no residue."""
    problems: list[str] = []
    for filename in CHART_SOURCE_FILES:
        path = output_dir / filename
        if not path.exists():
            problems.append(f"missing: {filename}")
            continue
        if path.stat().st_size == 0:
            problems.append(f"empty: {filename}")
            continue
        with path.open(newline="", encoding="utf-8") as handle:
            header = next(csv.reader(handle), [])
        missing = [column for column in CORE_COLUMNS if column not in header]
        if missing:
            problems.append(f"{filename} is missing column(s): {', '.join(missing)}")
    residue = sorted(p.name for p in output_dir.glob("*.tmp.*"))
    if residue:
        problems.append(f"temporary files left behind: {', '.join(residue)}")
    return problems


def resolve_destination(args: argparse.Namespace, repo_root: Path) -> tuple[Path, str]:
    """Destination and write mode for the requested engine."""
    if args.output is not None:
        return Path(args.output).expanduser(), CHART_SOURCE_WRITE_SCRATCH
    if args.engine == CANONICAL_CHART_SOURCE_ENGINE or args.allow_noncanonical_engine:
        return canonical_chart_source_dir(repo_root), CHART_SOURCE_WRITE_PROMOTE
    return engine_diagnostic_chart_source_dir(repo_root, args.engine), CHART_SOURCE_WRITE_SCRATCH


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).expanduser().resolve()
    data_root = Path(args.data_root).expanduser() if args.data_root else evidence_pack_root(repo_root, args.engine)
    output_dir, mode = resolve_destination(args, repo_root)
    canonical = canonical_chart_source_dir(repo_root)
    is_canonical = output_dir.resolve() == canonical.resolve() if output_dir.exists() else output_dir == canonical

    before = ped_calibration_r2(output_dir)

    print(f"engine            : {args.engine}")
    print(f"evidence pack     : {data_root}")
    print(f"destination       : {output_dir}")
    print(f"write mode        : {mode}")
    print(f"governed location : {is_canonical}")

    if not (data_root / "manifest.json").exists():
        print(f"FAIL no evidence pack manifest at {data_root}")
        return 2

    pack = load_evidence_pack(data_root, repo_root)

    if args.dry_run:
        # Render into a throwaway directory so the report is real without
        # touching the destination.
        scratch = Path(tempfile.mkdtemp(prefix="promote-chart-sources-dry-"))
        try:
            write_chart_source_tables(repo_root, pack.data, scratch, mode=CHART_SOURCE_WRITE_SCRATCH)
            after = ped_calibration_r2(scratch)
            problems = validate_output(scratch)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        wrote = False
    else:
        write_chart_source_tables(
            repo_root,
            pack.data,
            output_dir,
            mode=mode,
            engine=args.engine,
            allow_noncanonical_engine=args.allow_noncanonical_engine,
        )
        after = ped_calibration_r2(output_dir)
        problems = validate_output(output_dir)
        wrote = True

    print("\nPED calibration R2 (before -> after)")
    for basis in sorted(set(before) | set(after)):
        old = before.get(basis, "(absent)")
        new = after.get(basis, "(absent)")
        marker = "  " if old == new else "* "
        print(f"{marker}{basis}: {old} -> {new}")

    report: dict[str, Any] = {
        "engine": args.engine,
        "evidence_pack_root": str(data_root),
        "destination": str(output_dir),
        "write_mode": mode,
        "canonical_destination": bool(is_canonical),
        "dry_run": bool(args.dry_run),
        "wrote": wrote,
        "governed_files": list(GOVERNED_FILES),
        "ped_calibration_r2_before": before,
        "ped_calibration_r2_after": after,
        "validation_problems": problems,
    }
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if problems:
        print("\nFAIL validation problems:")
        for problem in problems:
            print(f"  {problem}")
        return 1

    print(f"\nPASS {len(CHART_SOURCE_FILES)} chart-source table(s) validated at {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

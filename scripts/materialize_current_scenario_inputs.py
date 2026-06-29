from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_dashboard.scenario_inputs import (  # noqa: E402
    SCENARIO_INPUT_DIRNAME,
    ScenarioWorkbookInput,
    materialize_scenario_inputs,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize promoted Revenue Outlook scenario workbook inputs into repo-local artifacts."
    )
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument(
        "--source-root",
        type=Path,
        action="append",
        default=[],
        help="Directory containing candidate source workbooks. May be supplied more than once.",
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.repo_root.resolve()
    output_dir = args.output_dir or root / "data" / "current_revenue_outlook" / SCENARIO_INPUT_DIRNAME
    manifest_path = root / "data" / "current_revenue_outlook" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    scenarios = manifest.get("source_comparison", {}).get("scenarios", [])
    if not isinstance(scenarios, list) or not scenarios:
        raise SystemExit("No source_comparison.scenarios found in current Revenue Outlook manifest.")

    source_roots = [path.resolve() for path in args.source_root]
    source_roots.append(root / "data" / "current_revenue_outlook" / SCENARIO_INPUT_DIRNAME / "raw")
    source_roots.append(root / "data" / "scenario_inputs" / "raw")

    workbook_inputs: list[ScenarioWorkbookInput] = []
    missing: list[str] = []
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            continue
        expected_hash = str(scenario.get("workbook_sha256") or "").lower()
        filename = str(scenario.get("workbook_filename") or "")
        match = _find_workbook_by_hash(source_roots, expected_hash)
        if match is None:
            missing.append(f"{scenario.get('scenario_name')} ({filename}, {expected_hash})")
            continue
        workbook_inputs.append(
            ScenarioWorkbookInput(
                workbook=match,
                scenario_name=str(scenario.get("scenario_name") or ""),
                scenario_role=str(scenario.get("scenario_role") or ""),
                workbook_filename=filename or match.name,
            )
        )

    if missing:
        raise SystemExit("Missing source workbooks for: " + "; ".join(missing))
    materialized = materialize_scenario_inputs(
        workbook_inputs,
        output_dir,
        created_by="materialize_current_scenario_inputs",
    )
    print(f"SCENARIO_INPUTS_MATERIALIZED {output_dir}")
    print(f"workbooks={len(materialized.get('workbooks', []))}")
    print(f"row_counts={materialized.get('row_counts', {})}")


def _find_workbook_by_hash(source_roots: list[Path], expected_hash: str) -> Path | None:
    if not expected_hash:
        return None
    for root in source_roots:
        if not root.exists():
            continue
        for path in root.glob("*.xlsx"):
            try:
                import hashlib

                actual = hashlib.sha256(path.read_bytes()).hexdigest().lower()
            except OSError:
                continue
            if actual == expected_hash:
                return path
    return None


if __name__ == "__main__":
    main()

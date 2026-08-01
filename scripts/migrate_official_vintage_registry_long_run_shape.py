"""Explicitly migrate the official-vintage registry to carry the shape role.

Section 3 of the anchored structural shape transition brief. PR #11 governs two
independent vintage roles - official comparator and bridge assumption. This
adds a third, ``is_default_long_run_shape_vintage``, plus the per-vintage
capability fields that decide which vintages may hold it.

The migration is explicit rather than implicit: capability
(``supports_long_run_shape`` and the FY window) is DERIVED from what each
vintage's committed pack actually publishes, while the default-role flag is a
governance decision applied by name. Re-running against an already-migrated
registry is a no-op.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from model_dashboard.official_vintage import (  # noqa: E402
    LONG_RUN_SHAPE_ROLE_FLAG,
    _derive_long_run_shape_support,
    load_official_vintage,
    registry_path,
    validate_official_vintage_registry,
)

DEFAULT_SHAPE_VINTAGE_ID = "BEFU26"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--default-shape-vintage",
        default=DEFAULT_SHAPE_VINTAGE_ID,
        help="vintage that becomes the default long-run shape source",
    )
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    args = parser.parse_args()

    root = Path(args.repo_root)
    path = registry_path(root)
    registry = json.loads(path.read_text(encoding="utf-8"))

    target = str(args.default_shape_vintage)
    known = {str(entry["vintage_id"]) for entry in registry["vintages"]}
    if target not in known:
        raise SystemExit(f"{target} is not registered; known vintages: {sorted(known)}")

    changed = False
    for entry in registry["vintages"]:
        vid = str(entry["vintage_id"])
        pack = load_official_vintage(vid, repo_root=root)
        if pack is None:
            raise SystemExit(
                f"{vid}: pack is not materialized, so its shape capability cannot be "
                "derived. Refusing to guess."
            )
        derived = _derive_long_run_shape_support(pack.official_annual, entry)
        derived.pop("long_run_shape_missing_series", None)
        derived["long_run_shape_required_series_available"] = bool(
            derived["supports_long_run_shape"]
        )
        derived[LONG_RUN_SHAPE_ROLE_FLAG] = vid == target
        for key, value in derived.items():
            if entry.get(key) != value:
                entry[key] = value
                changed = True
        print(
            f"{vid}: supports_long_run_shape={derived['supports_long_run_shape']} "
            f"window=FY{derived['long_run_shape_start_fy']}-FY{derived['long_run_shape_end_fy']} "
            f"default={derived[LONG_RUN_SHAPE_ROLE_FLAG]}"
        )

    registry["description"] = (
        "Governed registry of published official revenue-forecast vintages. Each "
        "entry maps a release round to its source workbook, layout, materialized "
        "pack and default-role flags. THREE roles are governed independently and "
        "exactly one vintage carries each: is_default_comparator (the published "
        "forecast displayed as the external comparator), is_default_bridge_vintage "
        "(effective rates, fuel intensity, administration, refunds, MVR, TUC and "
        "fixed lines used to turn Current activity into revenue) and "
        "is_default_long_run_shape_vintage (the external FY2031-FY2050 activity "
        "GROWTH SHAPE - never a level - used by the anchored structural shape "
        "transition). is_latest names the newest release. supports_long_run_shape "
        "and the long_run_shape_*_fy window are derived from what each pack "
        "actually publishes, so a later vintage becomes shape-capable without a "
        "code change. This registry names revenue-forecast vintages only; the "
        "Treasury BEFU26 macro path (treasury_befu26_macro_path.csv) is a separate "
        "macro-input vintage and is not registered here."
    )

    issues = validate_official_vintage_registry(registry)
    if issues:
        raise SystemExit("migrated registry fails validation: " + "; ".join(issues))

    if changed:
        path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {path}")
    else:
        print("registry already carries the long-run shape role; no change")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

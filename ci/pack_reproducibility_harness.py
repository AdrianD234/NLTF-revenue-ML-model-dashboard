"""Reusable governed-pack reproducibility harness.

Generalises ``ci/probe_uncertainty_rebuild_reproducibility.sh``'s comparison to
every governed pack.  Runs INSIDE the ``nltf-ci:local`` container (or any
environment with pandas + pyarrow); the driver script
``ci/probe_governed_pack_reproducibility.sh`` owns the clone/build lifecycle
and calls this module three ways:

    inventory  --pack-dir D --out inventory.json
    compare    --left A --right B --label X --out report.json
               [--diff-parquet diffs.parquet]

``compare`` classifies every file shared by the two snapshots:

    identical                     byte-for-byte equal
    provenance_only               JSON manifests differing only in fields that
                                  record HOW/WHERE the pack was built
    serialization_only            same parsed content, different bytes
                                  (line endings, float rendering, key order)
    value_movement                governed data values differ; magnitudes are
                                  reported, never suppressed
    schema_change                 columns/dtypes/row counts differ
    left_only / right_only        file present in one snapshot only

Nothing here mutates a pack.  Nothing here decides governance: it measures and
reports.  See artifacts/governed_artifact_reproducibility/ for the evidence
this produced and docs/FOLLOW_UP_PED_R2_DRIFT.md for why it exists.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Manifest fields that describe how/where/when a pack was built rather than
# what it contains.  A difference confined to these is provenance, not value
# movement — but it is still REPORTED field by field.
PROVENANCE_FIELDS = {
    "source_main_sha",
    "build_environment",
    "rebuild_command",
}

# Cap on materialised per-column diff records; the max-abs/max-rel statistics
# are always computed over every differing cell regardless of this cap.
_MAX_DIFF_RECORDS_PER_COLUMN = 500

# Preferred identifying columns, used to describe WHERE a frame first differs.
KEY_COLUMN_CANDIDATES = (
    "series_id",
    "FY",
    "period",
    "june_year",
    "quarter",
    "scenario_name",
    "scenario_role",
    "policy_state",
    "engine",
    "state_id",
    "stream",
    "component",
    "output_series_id",
    "metric",
    "name",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_files(root: Path) -> list[str]:
    return sorted(
        str(p.relative_to(root)).replace("\\", "/") for p in root.rglob("*") if p.is_file()
    )


def _parquet_summary(path: Path) -> dict[str, Any]:
    frame = pd.read_parquet(path)
    return {
        "rows": int(len(frame)),
        "columns": list(map(str, frame.columns)),
        "dtypes": {str(c): str(t) for c, t in frame.dtypes.items()},
    }


def inventory(pack_dir: Path) -> dict[str, Any]:
    entries: dict[str, Any] = {}
    for rel in _relative_files(pack_dir):
        path = pack_dir / rel
        entry: dict[str, Any] = {
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        if rel.endswith(".parquet"):
            try:
                entry["frame"] = _parquet_summary(path)
            except Exception as error:  # noqa: BLE001 - inventory must not die on one file
                entry["frame_error"] = str(error)
        entries[rel] = entry
    return {"root": str(pack_dir), "file_count": len(entries), "files": entries}


def _json_flat(value: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            out.update(_json_flat(item, f"{prefix}{key}." if prefix else f"{key}."))
        if not value:
            out[prefix.rstrip(".")] = {}
    else:
        out[prefix.rstrip(".")] = value
    return out


def _compare_json(left: Path, right: Path) -> dict[str, Any]:
    left_data = json.loads(left.read_text(encoding="utf-8"))
    right_data = json.loads(right.read_text(encoding="utf-8"))
    flat_left = _json_flat(left_data)
    flat_right = _json_flat(right_data)
    changed = sorted(
        key
        for key in set(flat_left) | set(flat_right)
        if flat_left.get(key, "<absent>") != flat_right.get(key, "<absent>")
    )
    if not changed:
        return {"classification": "serialization_only", "changed_fields": []}
    top_level = {key.split(".", 1)[0] for key in changed}
    classification = (
        "provenance_only" if top_level <= PROVENANCE_FIELDS else "value_movement"
    )
    return {
        "classification": classification,
        "changed_fields": [
            {
                "field": key,
                "left": flat_left.get(key, "<absent>"),
                "right": flat_right.get(key, "<absent>"),
            }
            for key in changed[:200]
        ],
    }


def _first_key_context(frame: pd.DataFrame, index: int) -> dict[str, Any]:
    keys = [c for c in KEY_COLUMN_CANDIDATES if c in frame.columns]
    if not keys:
        return {"row_index": int(index)}
    row = frame.iloc[index]
    context: dict[str, Any] = {"row_index": int(index)}
    for key in keys[:6]:
        value = row[key]
        context[key] = value.item() if hasattr(value, "item") else value
    return context


def _compare_parquet(
    left: Path, right: Path, rel: str
) -> tuple[dict[str, Any], pd.DataFrame | None]:
    left_frame = pd.read_parquet(left)
    right_frame = pd.read_parquet(right)
    result: dict[str, Any] = {
        "rows": [int(len(left_frame)), int(len(right_frame))],
    }
    if list(left_frame.columns) != list(right_frame.columns):
        result["classification"] = "schema_change"
        result["detail"] = {
            "left_columns": list(map(str, left_frame.columns)),
            "right_columns": list(map(str, right_frame.columns)),
        }
        return result, None
    dtype_changes = {
        str(c): [str(left_frame[c].dtype), str(right_frame[c].dtype)]
        for c in left_frame.columns
        if str(left_frame[c].dtype) != str(right_frame[c].dtype)
    }
    if dtype_changes:
        result["classification"] = "schema_change"
        result["detail"] = {"dtype_changes": dtype_changes}
        return result, None
    if len(left_frame) != len(right_frame):
        result["classification"] = "schema_change"
        result["detail"] = {"row_count_change": [int(len(left_frame)), int(len(right_frame))]}
        return result, None

    diff_rows: list[dict[str, Any]] = []
    max_abs = 0.0
    max_rel = 0.0
    first_divergence: dict[str, Any] | None = None
    cells_compared = 0
    cells_different = 0
    # The repo's structural closure contract (model_dashboard/
    # fuel_price_scenario.py): a difference within atol 1e-9 + rtol 1e-12*|x|
    # is inside every existing numerical guarantee. Counted vectorised over
    # EVERY differing cell, never just the recorded sample.
    cells_outside_contract = 0
    for column in left_frame.columns:
        lv = left_frame[column]
        rv = right_frame[column]
        if pd.api.types.is_float_dtype(lv) or pd.api.types.is_float_dtype(rv):
            la = pd.to_numeric(lv, errors="coerce").to_numpy(dtype=float)
            ra = pd.to_numeric(rv, errors="coerce").to_numpy(dtype=float)
            both_nan = np.isnan(la) & np.isnan(ra)
            unequal = ~both_nan & ~(la == ra)
        else:
            la = lv.to_numpy(dtype=object)
            ra = rv.to_numpy(dtype=object)
            unequal = np.array(
                [
                    not (
                        (x is None and y is None)
                        or (
                            isinstance(x, float)
                            and isinstance(y, float)
                            and math.isnan(x)
                            and math.isnan(y)
                        )
                        or x == y
                    )
                    for x, y in zip(la, ra)
                ],
                dtype=bool,
            )
        cells_compared += int(len(lv))
        n_unequal = int(unequal.sum())
        if n_unequal == 0:
            continue
        cells_different += n_unequal
        indices = np.flatnonzero(unequal)
        if first_divergence is None:
            first_divergence = {
                "column": str(column),
                **_first_key_context(left_frame, int(indices[0])),
            }
        numeric = pd.api.types.is_numeric_dtype(lv) and pd.api.types.is_numeric_dtype(rv)
        if numeric:
            # Vectorised stats over EVERY differing cell, so the reported
            # maxima never depend on the record cap below.
            l_num = pd.to_numeric(lv, errors="coerce").to_numpy(dtype=float)
            r_num = pd.to_numeric(rv, errors="coerce").to_numpy(dtype=float)
            abs_all = np.abs(r_num[indices] - l_num[indices])
            with np.errstate(divide="ignore", invalid="ignore"):
                rel_all = abs_all / np.abs(l_num[indices])
            finite_abs = abs_all[np.isfinite(abs_all)]
            finite_rel = rel_all[np.isfinite(rel_all)]
            if finite_abs.size:
                max_abs = max(max_abs, float(finite_abs.max()))
            if finite_rel.size:
                max_rel = max(max_rel, float(finite_rel.max()))
            tolerance = 1e-9 + 1e-12 * np.abs(l_num[indices])
            with np.errstate(invalid="ignore"):
                outside = abs_all > tolerance
            cells_outside_contract += int(np.nansum(outside))
        recorded = indices[:_MAX_DIFF_RECORDS_PER_COLUMN]
        for position, index in enumerate(recorded):
            lval = la[index]
            rval = ra[index]
            record: dict[str, Any] = {
                "file": rel,
                "column": str(column),
                **_first_key_context(left_frame, int(index)),
                "left": None if (isinstance(lval, float) and math.isnan(lval)) else lval,
                "right": None if (isinstance(rval, float) and math.isnan(rval)) else rval,
            }
            if numeric:
                abs_diff = float(abs_all[position])
                rel_diff = float(rel_all[position])
                if math.isfinite(abs_diff):
                    record["abs_diff"] = abs_diff
                if math.isfinite(rel_diff):
                    record["rel_diff"] = rel_diff
            diff_rows.append(record)
        if len(indices) > len(recorded):
            diff_rows.append(
                {
                    "file": rel,
                    "column": str(column),
                    "row_index": -1,
                    "left": f"<{len(indices) - len(recorded)} further differing cells omitted>",
                    "right": "",
                }
            )

    if cells_different == 0:
        result["classification"] = "serialization_only"
        return result, None
    result["classification"] = "value_movement"
    result["cells_compared"] = cells_compared
    result["cells_different"] = cells_different
    result["cells_outside_structural_contract"] = cells_outside_contract
    result["max_abs_diff"] = max_abs
    result["max_rel_diff"] = max_rel
    result["first_divergence"] = first_divergence
    diffs = pd.DataFrame(diff_rows)
    return result, diffs


def _compare_text(left: Path, right: Path) -> dict[str, Any]:
    left_bytes = left.read_bytes()
    right_bytes = right.read_bytes()
    if left_bytes.replace(b"\r\n", b"\n") == right_bytes.replace(b"\r\n", b"\n"):
        return {"classification": "serialization_only", "detail": "line endings only"}
    left_lines = left_bytes.replace(b"\r\n", b"\n").split(b"\n")
    right_lines = right_bytes.replace(b"\r\n", b"\n").split(b"\n")
    first = next(
        (
            i
            for i, (a, b) in enumerate(zip(left_lines, right_lines))
            if a != b
        ),
        min(len(left_lines), len(right_lines)),
    )
    return {
        "classification": "value_movement",
        "detail": {
            "first_differing_line": first + 1,
            "left_lines": len(left_lines),
            "right_lines": len(right_lines),
        },
    }


def compare(left_root: Path, right_root: Path, label: str) -> tuple[dict[str, Any], pd.DataFrame]:
    left_files = set(_relative_files(left_root))
    right_files = set(_relative_files(right_root))
    files: dict[str, Any] = {}
    all_diffs: list[pd.DataFrame] = []
    for rel in sorted(left_files | right_files):
        if rel not in right_files:
            files[rel] = {"classification": "left_only"}
            continue
        if rel not in left_files:
            files[rel] = {"classification": "right_only"}
            continue
        left_path = left_root / rel
        right_path = right_root / rel
        if sha256_file(left_path) == sha256_file(right_path):
            files[rel] = {"classification": "identical"}
            continue
        try:
            if rel.endswith(".json"):
                files[rel] = _compare_json(left_path, right_path)
            elif rel.endswith(".parquet"):
                result, diffs = _compare_parquet(left_path, right_path, rel)
                files[rel] = result
                if diffs is not None and not diffs.empty:
                    all_diffs.append(diffs)
            else:
                files[rel] = _compare_text(left_path, right_path)
        except Exception as error:  # noqa: BLE001 - report, do not die
            files[rel] = {"classification": "compare_error", "detail": str(error)}
    order = [
        "compare_error",
        "value_movement",
        "schema_change",
        "left_only",
        "right_only",
        "provenance_only",
        "serialization_only",
        "identical",
    ]
    classes = {info["classification"] for info in files.values()}
    overall = next((c for c in order if c in classes), "identical")
    report = {
        "label": label,
        "left": str(left_root),
        "right": str(right_root),
        "overall_classification": overall,
        "file_count": len(files),
        "class_counts": {
            c: sum(1 for info in files.values() if info["classification"] == c)
            for c in sorted(classes)
        },
        "files": files,
    }
    diffs_frame = (
        pd.concat(all_diffs, ignore_index=True) if all_diffs else pd.DataFrame()
    )
    if not diffs_frame.empty:
        # Mixed value types across frames (floats, strings, None) cannot share
        # one parquet column; the JSON report keeps native types, the parquet
        # evidence stores the values as text plus the numeric diff columns.
        for column in ("left", "right"):
            if column in diffs_frame.columns:
                diffs_frame[column] = diffs_frame[column].map(
                    lambda value: "" if value is None else repr(value)
                )
        for column in diffs_frame.columns:
            if column in ("abs_diff", "rel_diff"):
                continue
            if diffs_frame[column].dtype == object:
                diffs_frame[column] = diffs_frame[column].map(
                    lambda value: "" if value is None else str(value)
                )
    return report, diffs_frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_inv = sub.add_parser("inventory")
    p_inv.add_argument("--pack-dir", required=True)
    p_inv.add_argument("--out", required=True)

    p_cmp = sub.add_parser("compare")
    p_cmp.add_argument("--left", required=True)
    p_cmp.add_argument("--right", required=True)
    p_cmp.add_argument("--label", required=True)
    p_cmp.add_argument("--out", required=True)
    p_cmp.add_argument("--diff-parquet", default="")

    args = parser.parse_args()
    if args.command == "inventory":
        result = inventory(Path(args.pack_dir))
        Path(args.out).write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        print(f"inventory: {result['file_count']} files -> {args.out}")
        return

    report, diffs = compare(Path(args.left), Path(args.right), args.label)
    Path(args.out).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    if args.diff_parquet and not diffs.empty:
        diffs.to_parquet(args.diff_parquet, index=False)
    print(
        f"compare[{args.label}]: {report['overall_classification']} "
        f"({report['class_counts']})"
    )


if __name__ == "__main__":
    main()

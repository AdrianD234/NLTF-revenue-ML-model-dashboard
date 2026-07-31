"""Freeze the merged-main baseline the shape transition is measured against.

Section 4 of the brief. This MUST run before any candidate is calculated and
MUST read the committed packs as merged main left them - never a pack that has
already been rebuilt with a transition applied. Deriving the baseline from
post-rebuild packs would compare the change against itself and report ~0
falsely, which is exactly the failure mode the pinned actuals-refresh baseline
was introduced to prevent.

The generator is idempotent (same packs in, byte-identical CSV out) and fails
closed if it detects it is being run against a modified pack.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from model_dashboard.official_vintage import (  # noqa: E402
    LONG_RUN_SHAPE_METHOD_MANIFEST_KEY,
    load_official_vintage,
)
from model_dashboard.post_model_extrapolation import (  # noqa: E402
    ECONOMETRIC_SEGMENT,
    FIRST_EXTRAPOLATION_FY,
    LAST_EXTRAPOLATION_FY,
    POST_MODEL_SEGMENT,
)

OUT = REPO_ROOT / "artifacts" / "anchored_structural_shape_transition"

PACK_DIRS = {
    "ensemble": Path("data") / "current_revenue_outlook",
    "ar1": Path("data") / "engine_ar1" / "current_revenue_outlook",
}

BASELINE_ID = "anchored_structural_shape_transition_merged_main_baseline_v1"

# Everything the transition must leave untouched, plus the layer it replaces.
BASELINE_SEGMENTS = {
    "historical_actual": "actuals; must be identical after the change",
    "econometric_forecast": "Current FY2026-FY2030; must be identical after the change",
    "post_model_extrapolation": "the unblended FY2031-FY2050 layer being replaced",
    "official_comparator": "BEFU26 and MBU26 published rows; immutable",
}


class BaselineError(RuntimeError):
    """The baseline cannot be frozen from the current working tree."""


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _guard_pack_is_unmodified(engine: str, base: Path) -> dict[str, object]:
    """Refuse to freeze a baseline from a pack that already carries a shape."""

    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    block = manifest.get("official_vintages") or {}
    if LONG_RUN_SHAPE_METHOD_MANIFEST_KEY in block or "long_run_shape_vintage_id" in block:
        raise BaselineError(
            f"{engine}: the pack manifest already records a long-run shape role, so "
            "this pack has been rebuilt with the transition applied. Freezing a "
            "baseline from it would compare the change against itself. Restore the "
            "merged-main packs before running this."
        )
    return {
        "engine": engine,
        "pack_dir": base.relative_to(REPO_ROOT).as_posix(),
        "manifest_sha256": sha256_of(base / "manifest.json"),
        "official_comparator_vintage_id": block.get("official_comparator_vintage_id"),
        "bridge_assumption_vintage_id": block.get("bridge_assumption_vintage_id"),
    }


def _line_baseline_segment(frame: pd.DataFrame) -> pd.Series:
    """Classify line-reconciliation rows into the blocks the gates protect.

    The line table only stamps ``forecast_segment`` on post-model rows; the
    econometric FY2026-FY2030 Current rows are identified by their
    ``value_status`` (``current_finalist_forecast`` and the FY-nowcast
    variants). Classifying here rather than assuming a label means the
    "Current FY2026-FY2030 unchanged" gate actually has rows to compare.
    """

    status = frame["value_status"].fillna("").astype(str)
    segment = frame.get("forecast_segment", pd.Series("", index=frame.index))
    segment = segment.fillna("").astype(str)

    out = pd.Series("other", index=frame.index, dtype=object)
    out[status.str.lower().str.startswith("actual")] = "historical_actual"
    out[status.eq("official_forecast")] = "official_comparator"
    out[
        status.eq("current_finalist_forecast")
        | status.str.startswith("Current-finalist FY nowcast")
    ] = ECONOMETRIC_SEGMENT
    # The post-model label wins wherever it is present: those rows are the
    # layer being replaced, whatever their value_status says.
    out[segment.eq(POST_MODEL_SEGMENT)] = POST_MODEL_SEGMENT
    return out


def _line_rows(engine: str, base: Path) -> pd.DataFrame:
    frame = pd.read_parquet(base / "revenue_line_reconciliation.parquet")
    frame = frame.copy()
    frame["engine"] = engine
    if "forecast_segment" not in frame.columns:
        frame["forecast_segment"] = ""
    frame["forecast_segment"] = frame["forecast_segment"].fillna("").astype(str)
    frame["baseline_segment"] = _line_baseline_segment(frame)
    columns = [
        "engine",
        "source_path",
        "series_id",
        "FY",
        "value",
        "unit",
        "formula",
        "value_status",
        "forecast_segment",
        "baseline_segment",
        "source_basis",
    ]
    present = [column for column in columns if column in frame.columns]
    return frame[present]


def _chart_rows(engine: str, base: Path) -> pd.DataFrame:
    frame = pd.read_parquet(base / "revenue_chart_rows.parquet")
    frame = frame.copy()
    frame["engine"] = engine
    if "forecast_segment" not in frame.columns:
        frame["forecast_segment"] = ""
    frame["forecast_segment"] = frame["forecast_segment"].fillna("").astype(str)
    columns = [
        "engine",
        "scenario_name",
        "scenario_role",
        "series_id",
        "time_grain",
        "period",
        "june_year",
        "value",
        "value_status",
        "row_type",
        "forecast_segment",
    ]
    present = [column for column in columns if column in frame.columns]
    return frame[present]


def build_baseline() -> tuple[pd.DataFrame, list[dict[str, object]]]:
    line_frames: list[pd.DataFrame] = []
    chart_frames: list[pd.DataFrame] = []
    pack_records: list[dict[str, object]] = []

    for engine, relative in PACK_DIRS.items():
        base = REPO_ROOT / relative
        pack_records.append(_guard_pack_is_unmodified(engine, base))
        line_frames.append(_line_rows(engine, base))
        chart_frames.append(_chart_rows(engine, base))

    lines = pd.concat(line_frames, ignore_index=True)
    lines["baseline_block"] = "revenue_line_reconciliation"
    charts = pd.concat(chart_frames, ignore_index=True)
    charts["baseline_block"] = "revenue_chart_rows"

    # The official published rows come from the vintage packs themselves, not
    # from the runtime pack, so the immutability gate compares against the
    # SOURCE of truth rather than against a copy that the rebuild also writes.
    official_frames: list[pd.DataFrame] = []
    for vid in ("BEFU26", "MBU26"):
        pack = load_official_vintage(vid, repo_root=REPO_ROOT)
        if pack is None:
            raise BaselineError(f"{vid}: official vintage pack is not materialized.")
        frame = pack.official_annual.copy()
        frame["engine"] = "official"
        frame["official_vintage_id"] = vid
        frame["baseline_block"] = "official_vintage_official_annual"
        official_frames.append(
            frame[
                [
                    "engine",
                    "official_vintage_id",
                    "baseline_block",
                    "series_id",
                    "FY",
                    "value",
                ]
            ]
        )
    official = pd.concat(official_frames, ignore_index=True)

    baseline = pd.concat([lines, charts, official], ignore_index=True, sort=False)
    baseline = baseline.sort_values(
        [
            "baseline_block",
            "engine",
            "official_vintage_id",
            "source_path",
            "scenario_name",
            "baseline_segment",
            "series_id",
            "time_grain",
            "FY",
            "june_year",
            "period",
        ],
        na_position="last",
    ).reset_index(drop=True)
    return baseline, pack_records


def _assert_baseline_shape(baseline: pd.DataFrame) -> dict[str, object]:
    """Every block the transition must preserve has to be non-empty."""

    lines = baseline[baseline["baseline_block"].eq("revenue_line_reconciliation")]
    segments = lines["baseline_segment"].astype(str)
    counts = {
        "historical_actual_rows": int(segments.eq("historical_actual").sum()),
        "econometric_forecast_rows": int(segments.eq(ECONOMETRIC_SEGMENT).sum()),
        "post_model_extrapolation_rows": int(segments.eq(POST_MODEL_SEGMENT).sum()),
        "official_comparator_rows": int(segments.eq("official_comparator").sum()),
    }
    post = lines[segments.eq(POST_MODEL_SEGMENT)]
    fy = pd.to_numeric(post["FY"], errors="coerce")
    if not post.empty:
        counts["post_model_first_fy"] = int(fy.min())
        counts["post_model_last_fy"] = int(fy.max())
    official_rows = int(
        baseline["baseline_block"].eq("official_vintage_official_annual").sum()
    )
    counts["official_vintage_rows"] = official_rows

    for label, minimum in (
        ("historical_actual_rows", 1),
        ("econometric_forecast_rows", 1),
        ("post_model_extrapolation_rows", 1),
        ("official_comparator_rows", 1),
        ("official_vintage_rows", 1),
    ):
        if counts.get(label, 0) < minimum:
            raise BaselineError(
                f"baseline block {label} is empty; a vacuous baseline would make "
                "every downstream comparison trivially pass."
            )
    if counts.get("post_model_first_fy") != FIRST_EXTRAPOLATION_FY:
        raise BaselineError(
            f"post-model layer starts at FY{counts.get('post_model_first_fy')}, "
            f"expected FY{FIRST_EXTRAPOLATION_FY}."
        )
    if counts.get("post_model_last_fy") != LAST_EXTRAPOLATION_FY:
        raise BaselineError(
            f"post-model layer ends at FY{counts.get('post_model_last_fy')}, "
            f"expected FY{LAST_EXTRAPOLATION_FY}."
        )
    return counts


def _hash_frame(baseline: pd.DataFrame) -> pd.DataFrame:
    """A per-block, per-engine content hash so drift is attributable."""

    rows: list[dict[str, object]] = []
    grouped = baseline.groupby(
        ["baseline_block", "engine"], dropna=False, observed=True
    )
    for (block, engine), frame in grouped:
        payload = frame.drop(columns=["baseline_block"]).to_csv(
            index=False, float_format="%.17g"
        )
        rows.append(
            {
                "baseline_block": block,
                "engine": engine,
                "rows": int(len(frame)),
                "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            }
        )
    return pd.DataFrame(rows).sort_values(["baseline_block", "engine"]).reset_index(
        drop=True
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    baseline, pack_records = build_baseline()
    counts = _assert_baseline_shape(baseline)
    hashes = _hash_frame(baseline)

    baseline_path = OUT / "merged_main_baseline.csv"
    # %.17g guarantees a float64 round-trips through text exactly. pandas'
    # default formatter drops the last bits, which turned the "unchanged
    # exactly" gates into ~1e-12 comparisons - a precision artefact of the
    # baseline file rather than a real change. Writing full precision keeps
    # those gates true equalities.
    baseline.to_csv(baseline_path, index=False, float_format="%.17g")
    hashes.to_csv(OUT / "merged_main_baseline_hashes.csv", index=False)

    manifest = {
        "baseline_id": BASELINE_ID,
        "description": (
            "Hash-pinned merged-main baseline for the anchored structural shape "
            "transition. Frozen BEFORE any candidate was calculated, from the "
            "committed packs as PR #11 left them."
        ),
        "blocks": BASELINE_SEGMENTS,
        "packs": pack_records,
        "row_counts": counts,
        "total_rows": int(len(baseline)),
        "baseline_sha256": sha256_of(baseline_path),
        "regenerate_with": "scripts/build_anchored_shape_merged_baseline.py",
    }
    (OUT / "merged_main_baseline_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"row_counts": counts, "total_rows": len(baseline)}, indent=2))
    print(hashes.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

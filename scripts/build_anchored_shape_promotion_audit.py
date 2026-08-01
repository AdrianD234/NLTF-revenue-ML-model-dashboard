"""Prove the promotion moved only the FY2031-FY2050 layer.

Run AFTER rebuilding both packs on the production schedule. Compares the
rebuilt packs against the hash-pinned merged-main baseline frozen before any
candidate existed, and fails if anything outside the post-model layer moved.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from model_dashboard.long_run_shape_transition import (  # noqa: E402
    PRODUCTION_LONG_RUN_TRANSITION_SCHEDULE_ID,
)
from model_dashboard.official_vintage import load_official_vintage  # noqa: E402
from model_dashboard.post_model_extrapolation import (  # noqa: E402
    ANCHOR_FY,
    FIRST_EXTRAPOLATION_FY,
    LAST_EXTRAPOLATION_FY,
    POST_MODEL_SEGMENT,
)

OUT = REPO_ROOT / "artifacts" / "anchored_structural_shape_transition"
PACK_DIRS = {
    "ensemble": Path("data") / "current_revenue_outlook",
    "ar1": Path("data") / "engine_ar1" / "current_revenue_outlook",
}


def _baseline() -> pd.DataFrame:
    return pd.read_csv(
        OUT / "merged_main_baseline.csv", float_precision="round_trip"
    )


def _line_segment(frame: pd.DataFrame) -> pd.Series:
    status = frame["value_status"].fillna("").astype(str)
    segment = frame.get("forecast_segment", pd.Series("", index=frame.index))
    segment = segment.fillna("").astype(str)
    out = pd.Series("other", index=frame.index, dtype=object)
    out[status.str.lower().str.startswith("actual")] = "historical_actual"
    out[status.eq("official_forecast")] = "official_comparator"
    out[
        status.eq("current_finalist_forecast")
        | status.str.startswith("Current-finalist FY nowcast")
    ] = "econometric_forecast"
    out[segment.eq(POST_MODEL_SEGMENT)] = POST_MODEL_SEGMENT
    return out


def main() -> int:
    baseline = _baseline()
    findings: list[dict[str, object]] = []
    problems: list[str] = []

    for engine, relative in PACK_DIRS.items():
        base = REPO_ROOT / relative
        manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
        block = manifest.get("official_vintages") or {}
        schedule = str(block.get("long_run_transition_schedule_id") or "")
        if schedule != PRODUCTION_LONG_RUN_TRANSITION_SCHEDULE_ID:
            problems.append(
                f"{engine}: pack records schedule {schedule!r}, expected "
                f"{PRODUCTION_LONG_RUN_TRANSITION_SCHEDULE_ID!r}"
            )

        live = pd.read_parquet(base / "revenue_line_reconciliation.parquet")
        live = live.copy()
        live["segment"] = _line_segment(live)
        frozen = baseline[
            baseline["baseline_block"].eq("revenue_line_reconciliation")
            & baseline["engine"].eq(engine)
        ]
        merged = frozen.merge(
            live,
            on=["source_path", "series_id", "FY"],
            suffixes=("_frozen", "_live"),
        )
        if merged.empty:
            problems.append(f"{engine}: baseline/live join is empty")
            continue

        delta = (
            pd.to_numeric(merged["value_frozen"], errors="coerce")
            - pd.to_numeric(merged["value_live"], errors="coerce")
        ).abs()
        changed = merged[delta > 1e-9]
        unchanged_segments = sorted(
            set(changed["baseline_segment"].astype(str).unique())
            - {POST_MODEL_SEGMENT}
        )
        if unchanged_segments:
            problems.append(
                f"{engine}: segments outside the post-model layer moved: "
                f"{unchanged_segments}"
            )
        fy = pd.to_numeric(changed["FY"], errors="coerce")
        outside = changed[
            ~fy.between(FIRST_EXTRAPOLATION_FY, LAST_EXTRAPOLATION_FY)
        ]
        if not outside.empty:
            problems.append(
                f"{engine}: {len(outside)} rows changed outside "
                f"FY{FIRST_EXTRAPOLATION_FY}-FY{LAST_EXTRAPOLATION_FY}"
            )

        findings.append(
            {
                "engine": engine,
                "recorded_schedule": schedule,
                "recorded_shape_vintage": block.get("long_run_shape_vintage_id"),
                "joined_rows": int(len(merged)),
                "changed_rows": int(len(changed)),
                "changed_segments": sorted(
                    changed["baseline_segment"].astype(str).unique()
                ),
                "changed_fy_min": int(fy.min()) if len(changed) else None,
                "changed_fy_max": int(fy.max()) if len(changed) else None,
                "max_abs_delta": float(delta.max()),
            }
        )

        # Official published rows must be byte-identical to their source packs.
        for vid in ("BEFU26", "MBU26"):
            pack = load_official_vintage(vid, repo_root=REPO_ROOT)
            assert pack is not None
            frozen_official = baseline[
                baseline["baseline_block"].eq("official_vintage_official_annual")
                & baseline["official_vintage_id"].eq(vid)
            ]
            official = frozen_official.merge(
                pack.official_annual, on=["series_id", "FY"], suffixes=("_f", "_l")
            )
            if not np.array_equal(
                official["value_f"].to_numpy(dtype=float),
                official["value_l"].to_numpy(dtype=float),
                equal_nan=True,
            ):
                problems.append(f"{vid}: published official rows changed")

    frame = pd.DataFrame(findings)
    frame.to_csv(OUT / "promotion_impact_audit.csv", index=False)
    print(frame.to_string(index=False))

    # The promotion must actually DO something, or the audit is vacuous.
    if frame["changed_rows"].sum() == 0:
        problems.append("no rows changed; the promotion had no effect")

    if problems:
        print()
        for problem in problems:
            print("FAIL:", problem)
        return 1
    print()
    print(
        "PASS: only FY2031-FY2050 post-model rows moved; actuals, the "
        "econometric window and both official spines are unchanged"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

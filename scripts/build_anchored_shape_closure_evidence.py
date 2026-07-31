"""Emit the remaining committed evidence for the shape transition.

Sections 12, 13 and 16: the comparison against the reconstructed legacy
structural curves, the permanent three-role independence matrix, and the
front-end preview audit.
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
    SCHEDULES,
    UNBLENDED_SCHEDULE_ID,
)
from model_dashboard.official_vintage import (  # noqa: E402
    ROLE_FLAGS,
    load_official_vintage,
)
from model_dashboard.post_model_extrapolation import (  # noqa: E402
    build_post_model_extrapolation_annual,
)

OUT = REPO_ROOT / "artifacts" / "anchored_structural_shape_transition"
PACK_DIR = REPO_ROOT / "data" / "current_revenue_outlook"
BASE_SCENARIO = "current_basecase"
POOL_CLASSES = ("light_ruc_net_km", "light_bev_ruc_net_km", "phev_ruc_net_km")
ACTIVITY_SERIES = (
    "light_petrol_vkt",
    "ped_vkt_per_capita",
    "heavy_ruc_net_km",
    *POOL_CLASSES,
)


def _inputs() -> dict[str, pd.DataFrame]:
    return {
        "line_reconciliation": pd.read_parquet(
            PACK_DIR / "revenue_line_reconciliation.parquet"
        ),
        "raw_quarterly_audit": pd.read_parquet(
            PACK_DIR / "raw_quarterly_forecast_audit.parquet"
        ),
        "scenario_input_wide": pd.read_parquet(
            PACK_DIR / "scenario_inputs" / "scenario_input_wide.parquet"
        ),
    }


def _build(inputs, packs, *, bridge: str, shape: str, schedule: str) -> pd.DataFrame:
    return build_post_model_extrapolation_annual(
        line_reconciliation=inputs["line_reconciliation"],
        raw_quarterly_audit=inputs["raw_quarterly_audit"],
        scenario_input_wide=inputs["scenario_input_wide"],
        mbu26_official_annual=packs[bridge].official_annual,
        repo_root=REPO_ROOT,
        long_run_shape_official_annual=packs[shape].official_annual,
        long_run_shape_vintage_id=shape,
        transition_schedule_id=schedule,
    )


def comparison_to_legacy(candidates: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Candidate BEV share of the Light RUC pool vs the reconstructed curves.

    The legacy workbook validated a COMPOSITION path, so the like-for-like
    comparison is on the BEV share of the pool - not on levels, which the
    workbook never spoke to.
    """

    legacy = pd.read_csv(OUT / "legacy_vfm_mbu_share_comparison.csv")
    legacy = legacy.set_index("june_year")
    rows: list[dict[str, object]] = []
    for candidate_id, frame in candidates.items():
        wide = frame[frame["scenario_name"].eq(BASE_SCENARIO)].pivot_table(
            index="fy", columns="series_id", values="value"
        )
        pool = sum(wide[column] for column in POOL_CLASSES)
        bev_share = wide["light_bev_ruc_net_km"] / pool
        for fy in wide.index:
            if fy not in legacy.index:
                continue
            row = legacy.loc[fy]
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "june_year": int(fy),
                    "candidate_bev_share_of_pool": float(bev_share.loc[fy]),
                    "legacy_mot_mbu26_bev_share": float(
                        row["mot_mbu26_official_bev_share"]
                    ),
                    "legacy_vfm_base_bev_share": float(row["vfm_base_bev_share"]),
                    "legacy_dashboard_curve_bev_share": float(
                        row["dashboard_dial_curve_bev_share"]
                    ),
                    "candidate_minus_legacy_curve_pp": (
                        float(bev_share.loc[fy])
                        - float(row["dashboard_dial_curve_bev_share"])
                    )
                    * 100.0,
                    "candidate_minus_vfm_base_pp": (
                        float(bev_share.loc[fy]) - float(row["vfm_base_bev_share"])
                    )
                    * 100.0,
                    "note": (
                        "composition comparison only; the legacy workbook validated "
                        "a share path, never a level or a revenue total"
                    ),
                }
            )
    return pd.DataFrame(rows)


def role_independence_matrix(inputs, packs) -> pd.DataFrame:
    """The permanent comparator x bridge x shape matrix, as committed evidence."""

    cells = (
        ("BEFU26", "BEFU26", "BEFU26"),
        ("MBU26", "BEFU26", "BEFU26"),
        ("BEFU26", "MBU26", "BEFU26"),
        ("BEFU26", "BEFU26", "MBU26"),
    )
    reference = _build(
        inputs, packs, bridge="BEFU26", shape="BEFU26", schedule="balanced_structural"
    )

    def _vector(frame: pd.DataFrame, series: str) -> np.ndarray:
        scoped = frame[
            frame["scenario_name"].eq(BASE_SCENARIO) & frame["series_id"].eq(series)
        ]
        return scoped.sort_values("fy")["value"].to_numpy(dtype=float)

    rows: list[dict[str, object]] = []
    for comparator, bridge, shape in cells:
        frame = _build(
            inputs, packs, bridge=bridge, shape=shape, schedule="balanced_structural"
        )
        activity_delta = max(
            float(np.abs(_vector(frame, series) - _vector(reference, series)).max())
            for series in ACTIVITY_SERIES
        )
        revenue_delta = float(
            np.abs(
                _vector(frame, "total_nltf_net_revenue")
                - _vector(reference, "total_nltf_net_revenue")
            ).max()
        )
        rows.append(
            {
                "comparator_vintage_id": comparator,
                "bridge_vintage_id": bridge,
                "long_run_shape_vintage_id": shape,
                "transition_schedule_id": "balanced_structural",
                "max_activity_delta_vs_reference": activity_delta,
                "max_total_nltf_delta_vs_reference": revenue_delta,
                "activity_changed": activity_delta > 0.0,
                "revenue_changed": revenue_delta > 0.0,
                "expected_activity_changed": shape != "BEFU26",
                "expected_revenue_changed": shape != "BEFU26" or bridge != "BEFU26",
                "comparator_affects_current": False,
                "official_published_rows_changed": False,
            }
        )
    frame = pd.DataFrame(rows)
    mismatches = frame[
        (frame["activity_changed"] != frame["expected_activity_changed"])
        | (frame["revenue_changed"] != frame["expected_revenue_changed"])
    ]
    if not mismatches.empty:
        raise SystemExit(
            "role independence matrix does not behave as specified:\n"
            + mismatches.to_string(index=False)
        )
    return frame


def front_end_preview_audit() -> pd.DataFrame:
    """What the analyst selector offers, and which layer each option moves."""

    import app as dashboard

    manifest = json.loads((PACK_DIR / "manifest.json").read_text(encoding="utf-8"))
    options = dashboard._long_run_shape_preview_options(manifest)
    rows: list[dict[str, object]] = []
    for label, spec in options.items():
        state = {
            "schedule_id": spec["schedule_id"],
            "shape_vintage_id": spec["shape_vintage_id"],
            "anchor_fy": 2030,
            "completion_fy": None,
        }
        rows.append(
            {
                "option_label": label,
                "transition_schedule_id": spec["schedule_id"],
                "long_run_shape_vintage_id": spec["shape_vintage_id"],
                "role": spec["role"],
                "is_pack_default": spec["is_pack_default"],
                "changes_layer": "current_fy2031_fy2050_activity_and_revenue",
                "changes_official_rows": False,
                "changes_current_fy2026_fy2030": False,
                "analyst_only": True,
                "details_text": dashboard._long_run_shape_details_text(
                    state, "Base_EV"
                ).replace("  \n", " | "),
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    inputs = _inputs()
    packs = {}
    for vid in ("BEFU26", "MBU26"):
        pack = load_official_vintage(vid, repo_root=REPO_ROOT)
        assert pack is not None, vid
        packs[vid] = pack

    candidates = {
        schedule_id: _build(
            inputs, packs, bridge="BEFU26", shape="BEFU26", schedule=schedule_id
        )
        for schedule_id in SCHEDULES
    }

    comparison_to_legacy(candidates).to_csv(
        OUT / "candidate_comparison_to_legacy.csv", index=False
    )
    matrix = role_independence_matrix(inputs, packs)
    matrix.to_csv(OUT / "role_independence_matrix.csv", index=False)
    preview = front_end_preview_audit()
    preview.to_csv(OUT / "front_end_preview_audit.csv", index=False)

    registry_roles = pd.DataFrame(
        [
            {
                "vintage_id": entry["vintage_id"],
                **{flag: bool(entry.get(flag)) for flag in ROLE_FLAGS},
                "supports_long_run_shape": bool(entry.get("supports_long_run_shape")),
                "long_run_shape_start_fy": entry.get("long_run_shape_start_fy"),
                "long_run_shape_end_fy": entry.get("long_run_shape_end_fy"),
            }
            for entry in json.loads(
                (
                    REPO_ROOT
                    / "data"
                    / "revenue_model_source_pack"
                    / "official_vintage_registry.json"
                ).read_text(encoding="utf-8")
            )["vintages"]
        ]
    )
    registry_roles.to_csv(OUT / "governed_vintage_roles.csv", index=False)

    print(matrix.to_string(index=False))
    print()
    print(preview[["option_label", "transition_schedule_id", "role"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

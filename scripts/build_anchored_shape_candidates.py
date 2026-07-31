"""Build and score the four governed long-run shape candidates.

Sections 6, 7, 12 and 16 of the brief. Every candidate is constructed through
the same governed constructor and the same formula registry; the ONLY thing
that varies is the transition schedule (and, for the audit legs, the shape
vintage or the VFM composition scenario).

Nothing here promotes a candidate. The production default stays
``unblended_current`` until the owner selects one.
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

from model_dashboard.mbu26_source_spine import FORMULA_DEFINITIONS  # noqa: E402
from model_dashboard.long_run_shape_transition import (  # noqa: E402
    SCHEDULES,
    UNBLENDED_SCHEDULE_ID,
    schedule_catalogue_frame,
    transition_weight_candidates_frame,
)
from model_dashboard.official_vintage import (  # noqa: E402
    default_long_run_shape_vintage_id,
    load_official_vintage,
)
from model_dashboard.post_model_extrapolation import (  # noqa: E402
    ANCHOR_FY,
    FIRST_EXTRAPOLATION_FY,
    LAST_EXTRAPOLATION_FY,
    anchor_shape_level_audit,
    build_post_model_extrapolation_annual,
    light_fleet_composition_audit,
    post_model_growth_indices,
)

OUT = REPO_ROOT / "artifacts" / "anchored_structural_shape_transition"
PACK_DIR = REPO_ROOT / "data" / "current_revenue_outlook"
BASE_SCENARIO = "current_basecase"

# The series the decision table and the candidate paths report on.
REPORTED_SERIES: tuple[str, ...] = (
    "light_petrol_vkt",
    "ped_vkt_per_capita",
    "ped_volume",
    "light_ruc_net_km",
    "light_bev_ruc_net_km",
    "phev_ruc_net_km",
    "heavy_ruc_net_km",
    "net_fed_revenue",
    "total_ruc_net_revenue",
    "net_mvr_revenue",
    "tuc_net_revenue",
    "total_nltf_net_revenue",
)
POOL_CLASSES = ("light_ruc_net_km", "light_bev_ruc_net_km", "phev_ruc_net_km")
REPORT_FYS = (2030, 2031, 2035, 2040, 2045, 2050)


def _pack_inputs() -> dict[str, pd.DataFrame]:
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


def _anchor_row(line_reconciliation: pd.DataFrame, series: str) -> float:
    scoped = line_reconciliation[
        line_reconciliation["source_path"].eq("Current finalist Base case")
        & pd.to_numeric(line_reconciliation["FY"], errors="coerce").eq(ANCHOR_FY)
        & line_reconciliation["series_id"].eq(series)
    ]
    return float(pd.to_numeric(scoped["value"], errors="coerce").iloc[0])


def build_candidates(
    inputs: dict[str, pd.DataFrame],
    bridge_annual: pd.DataFrame,
    shape_annual: pd.DataFrame,
    shape_vintage_id: str,
) -> dict[str, pd.DataFrame]:
    candidates: dict[str, pd.DataFrame] = {}
    for schedule_id in SCHEDULES:
        candidates[schedule_id] = build_post_model_extrapolation_annual(
            line_reconciliation=inputs["line_reconciliation"],
            raw_quarterly_audit=inputs["raw_quarterly_audit"],
            scenario_input_wide=inputs["scenario_input_wide"],
            mbu26_official_annual=bridge_annual,
            repo_root=REPO_ROOT,
            long_run_shape_official_annual=shape_annual,
            long_run_shape_vintage_id=shape_vintage_id,
            transition_schedule_id=schedule_id,
        )
    return candidates


def candidate_paths_frame(candidates: dict[str, pd.DataFrame]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for candidate_id, frame in candidates.items():
        scoped = frame[frame["series_id"].isin(REPORTED_SERIES)].copy()
        scoped["candidate_id"] = candidate_id
        frames.append(
            scoped[
                [
                    "candidate_id",
                    "scenario_name",
                    "scenario_role",
                    "fy",
                    "series_id",
                    "value",
                    "unit",
                    "long_run_transition_schedule_id",
                    "long_run_shape_vintage_id",
                    "fleet_composition_scenario",
                ]
            ]
        )
    out = pd.concat(frames, ignore_index=True)
    pools = (
        out[out["series_id"].isin(POOL_CLASSES)]
        .groupby(["candidate_id", "scenario_name", "fy"], as_index=False)["value"]
        .sum()
    )
    pools["series_id"] = "light_ruc_total_pool"
    pools["unit"] = "million km"
    return pd.concat([out, pools], ignore_index=True, sort=False)


def _anchor_values(inputs: dict[str, pd.DataFrame]) -> dict[str, float]:
    line = inputs["line_reconciliation"]
    anchors = {series: _anchor_row(line, series) for series in REPORTED_SERIES}
    anchors["light_ruc_total_pool"] = sum(
        _anchor_row(line, series) for series in POOL_CLASSES
    )
    return anchors


def transition_metrics_frame(
    paths: pd.DataFrame,
    anchors: dict[str, float],
    official_wide: pd.DataFrame,
) -> pd.DataFrame:
    """Seam growth, milestone levels, growth rates and the official ratio."""

    rows: list[dict[str, object]] = []
    base = paths[paths["scenario_name"].eq(BASE_SCENARIO)]
    for (candidate_id, series_id), frame in base.groupby(["candidate_id", "series_id"]):
        by_fy = frame.set_index("fy")["value"].sort_index()
        anchor = anchors.get(series_id, np.nan)
        record: dict[str, object] = {
            "candidate_id": candidate_id,
            "series_id": series_id,
            "fy2030_anchor": anchor,
        }
        for fy in REPORT_FYS:
            if fy in by_fy.index:
                record[f"fy{fy}"] = float(by_fy.loc[fy])
        if np.isfinite(anchor) and anchor != 0.0 and FIRST_EXTRAPOLATION_FY in by_fy.index:
            record["fy2031_seam_growth"] = float(
                by_fy.loc[FIRST_EXTRAPOLATION_FY] / anchor - 1.0
            )
        steps = by_fy.pct_change().dropna()
        if len(steps):
            record["max_annual_growth"] = float(steps.max())
            record["min_annual_growth"] = float(steps.min())
            # Curvature: how many times the year-on-year growth changes sign.
            signs = np.sign(steps.to_numpy())
            active = signs[signs != 0]
            record["growth_sign_changes"] = int(np.sum(np.diff(active) != 0))
        official_series = _official_equivalent(series_id, official_wide)
        if official_series is not None:
            for fy in (2040, 2050):
                if fy in by_fy.index and fy in official_series.index:
                    official_value = float(official_series.loc[fy])
                    if official_value != 0.0:
                        record[f"ratio_to_official_fy{fy}"] = (
                            float(by_fy.loc[fy]) / official_value
                        )
            if ANCHOR_FY in official_series.index and float(
                official_series.loc[ANCHOR_FY]
            ) != 0.0:
                record["anchor_ratio_to_official"] = anchor / float(
                    official_series.loc[ANCHOR_FY]
                )
        rows.append(record)
    return pd.DataFrame(rows).sort_values(["series_id", "candidate_id"]).reset_index(
        drop=True
    )


def _official_equivalent(series_id: str, wide: pd.DataFrame) -> pd.Series | None:
    if series_id == "light_ruc_total_pool":
        needed = list(POOL_CLASSES)
        if not all(column in wide.columns for column in needed):
            return None
        return wide[needed].sum(axis=1)
    if series_id in wide.columns:
        return wide[series_id]
    return None


def formula_reconciliation_frame(candidates: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Recompute every aggregate from the GOVERNED formula registry.

    The expected identities are evaluated generically from
    ``FORMULA_DEFINITIONS`` - the same registry the constructor and the MBU26
    spine are governed by - rather than from a second list maintained here. A
    local copy would be independent of the constructor but NOT independently
    governed: if the canonical registry changed, the constructor and this audit
    could drift together while the audit still passed, proving nothing about
    the authoritative contract.

    This stays independent of the constructor in the way that matters: the
    constructor writes each aggregate out longhand, while this evaluates the
    registry's signed ``terms`` generically. Agreement is therefore evidence,
    not tautology.
    """

    rows: list[dict[str, object]] = []
    evaluated: set[str] = set()
    for candidate_id, frame in candidates.items():
        wide = frame.pivot_table(
            index=["scenario_name", "fy"], columns="series_id", values="value"
        )
        for definition in FORMULA_DEFINITIONS:
            target = str(definition["output_series_id"])
            terms = definition["terms"]
            if target not in wide.columns:
                continue
            missing = [series for series, _ in terms if series not in wide.columns]
            if missing:
                raise SystemExit(
                    f"{candidate_id}: {target} cannot be reconciled; the governed "
                    f"registry needs {missing}, which the layer does not emit."
                )
            evaluated.add(target)
            recomputed = sum(
                float(coefficient) * wide[series] for series, coefficient in terms
            )
            residual = wide[target] - recomputed
            for (scenario, fy), value in residual.items():
                rows.append(
                    {
                        "candidate_id": candidate_id,
                        "scenario_name": scenario,
                        "fy": int(fy),
                        "series_id": target,
                        "governed_expression": str(definition["expression"]),
                        "published_value": float(wide.at[(scenario, fy), target]),
                        "registry_recomputed": float(recomputed.loc[(scenario, fy)]),
                        "residual": float(value),
                    }
                )

    out = pd.DataFrame(rows)
    if out.empty:
        raise SystemExit("formula reconciliation produced no rows; the join is vacuous.")

    # Non-vacuity: every governed aggregate the layer emits must have been
    # checked, so a silently dropped identity cannot pass as a clean audit.
    emitted = {
        str(series)
        for frame in candidates.values()
        for series in frame["series_id"].unique()
    }
    governed = {str(d["output_series_id"]) for d in FORMULA_DEFINITIONS}
    unchecked = sorted((governed & emitted) - evaluated)
    if unchecked:
        raise SystemExit(
            f"governed aggregates emitted but not reconciled: {unchecked}"
        )

    worst = float(out["residual"].abs().max())
    # The governed reconciliation tolerance elsewhere in the repo is 1e-6.
    if worst > 1e-6:
        raise SystemExit(
            f"formula reconciliation failed: worst residual {worst:.3e} exceeds 1e-6"
        )
    return out


def activity_identity_frame(
    candidates: dict[str, pd.DataFrame],
    inputs: dict[str, pd.DataFrame],
    shape_annual: pd.DataFrame,
    shape_vintage_id: str,
) -> pd.DataFrame:
    """Check emitted activity against INDEPENDENTLY derived expectations.

    Both checks here deliberately avoid the circularity of deriving the
    expectation from the very outputs under test:

    - the expected Light RUC pool is the FY2030 Current pool anchor times the
      hybrid pool index, recomputed from the growth-index frame, and the three
      emitted classes are compared against THAT - not against their own sum,
      which cannot fail;
    - the expected population comes from the committed scenario-input path
      aggregated by the governed annual method, not from dividing
      light_petrol_vkt by ped_vkt_per_capita, which would test nothing.
    """

    rows: list[dict[str, object]] = []
    for candidate_id, frame in candidates.items():
        for scenario in sorted(frame["scenario_name"].astype(str).unique()):
            growth = post_model_growth_indices(
                inputs["raw_quarterly_audit"],
                inputs["scenario_input_wide"],
                scenario_name=scenario,
                repo_root=REPO_ROOT,
                long_run_shape_official_annual=shape_annual,
                long_run_shape_vintage_id=shape_vintage_id,
                transition_schedule_id=candidate_id,
            ).set_index("fy")
            anchors = _scenario_anchors(inputs["line_reconciliation"], scenario)
            pool_anchor = sum(anchors[series] for series in POOL_CLASSES)
            population = _scenario_annual_population(
                inputs["scenario_input_wide"], inputs["raw_quarterly_audit"], scenario
            )

            wide = frame[frame["scenario_name"].eq(scenario)].pivot_table(
                index="fy", columns="series_id", values="value"
            )
            for fy in wide.index:
                expected_pool = pool_anchor * float(growth.at[fy, "h_light_ruc_pool"])
                emitted_classes = sum(
                    float(wide.at[fy, column]) for column in POOL_CLASSES
                )
                expected_population = float(population.loc[fy])
                expected_petrol = (
                    float(wide.at[fy, "ped_vkt_per_capita"])
                    * expected_population
                    / 1_000_000.0
                )
                rows.append(
                    {
                        "candidate_id": candidate_id,
                        "scenario_name": scenario,
                        "fy": int(fy),
                        "pool_anchor_fy2030": pool_anchor,
                        "hybrid_pool_index": float(growth.at[fy, "h_light_ruc_pool"]),
                        "expected_pool_million_km": expected_pool,
                        "emitted_class_sum_million_km": emitted_classes,
                        "class_sum_residual": emitted_classes - expected_pool,
                        "scenario_population_from_input_path": expected_population,
                        "emitted_light_petrol_vkt": float(
                            wide.at[fy, "light_petrol_vkt"]
                        ),
                        "expected_light_petrol_vkt": expected_petrol,
                        "ped_identity_residual": float(wide.at[fy, "light_petrol_vkt"])
                        - expected_petrol,
                    }
                )

    out = pd.DataFrame(rows)
    worst_pool = float(out["class_sum_residual"].abs().max())
    worst_ped = float(out["ped_identity_residual"].abs().max())
    scale = float(out["expected_pool_million_km"].abs().max())
    tolerance = 1e-9 * max(1.0, scale)
    if worst_pool > tolerance:
        raise SystemExit(
            f"Light classes do not sum to the independently computed hybrid pool "
            f"(worst {worst_pool:.3e} > {tolerance:.3e})"
        )
    if worst_ped > tolerance:
        raise SystemExit(
            "light_petrol_vkt does not equal VKTpc x the scenario-input population "
            f"(worst {worst_ped:.3e} > {tolerance:.3e})"
        )
    return out


def _scenario_anchors(
    line_reconciliation: pd.DataFrame, scenario: str
) -> dict[str, float]:
    source_path = {
        "current_basecase": "Current finalist Base case",
        "current_comparison_1": "Current finalist High population/comparison",
    }[scenario]
    scoped = line_reconciliation[
        line_reconciliation["source_path"].eq(source_path)
        & pd.to_numeric(line_reconciliation["FY"], errors="coerce").eq(ANCHOR_FY)
    ]
    return {
        str(row.series_id): float(row.value)
        for row in scoped.itertuples()
        if pd.notna(row.value)
    }


def _scenario_annual_population(
    scenario_input_wide: pd.DataFrame,
    raw_quarterly_audit: pd.DataFrame,
    scenario: str,
) -> pd.Series:
    """The scenario's own annual population, from the committed INPUT paths.

    Aggregated by the governed annual method: the VKT-weighted mean of the
    quarterly population, which is the definition under which
    ``petrol = VKTpc x population`` holds at every FY including the anchor.

    Both ingredients are inputs, not outputs: the quarterly population comes
    from the committed scenario-input frame and the quarterly VKTpc weights
    from the raw long-horizon audit path. Neither is the emitted
    ``light_petrol_vkt`` or ``ped_vkt_per_capita`` being checked, so the
    comparison can actually fail.
    """

    population = scenario_input_wide[
        scenario_input_wide["scenario_name"].astype(str).eq(scenario)
        & scenario_input_wide["stream"].astype(str).eq("PED")
    ][["canonical_period", "population"]].copy()
    population["population"] = pd.to_numeric(population["population"], errors="coerce")

    vktpc = raw_quarterly_audit[
        raw_quarterly_audit["scenario_name"].astype(str).eq(scenario)
        & raw_quarterly_audit["series_id"].astype(str).eq("ped_vkt_per_capita")
    ][["period", "value"]].copy()
    vktpc["value"] = pd.to_numeric(vktpc["value"], errors="coerce")

    merged = vktpc.merge(
        population, left_on="period", right_on="canonical_period", how="inner"
    )
    if merged.empty:
        raise SystemExit(
            f"{scenario}: no quarters join the raw VKTpc path to the scenario "
            "population path; the PED identity check would be vacuous."
        )
    merged["fy"] = merged["period"].astype(str).map(_fy_of_quarter)
    weighted = (merged["value"] * merged["population"]).groupby(merged["fy"]).sum()
    weights = merged["value"].groupby(merged["fy"]).sum()
    return weighted / weights


def _fy_of_quarter(period: str) -> int:
    year, quarter = int(str(period)[:4]), int(str(period)[5])
    return year + 1 if quarter >= 3 else year


def scorecard_frame(
    metrics: pd.DataFrame, weights: pd.DataFrame, paths: pd.DataFrame
) -> pd.DataFrame:
    """One row per candidate with the assessment criteria the brief names."""

    rows: list[dict[str, object]] = []
    nltf = metrics[metrics["series_id"].eq("total_nltf_net_revenue")].set_index(
        "candidate_id"
    )
    petrol = metrics[metrics["series_id"].eq("light_petrol_vkt")].set_index(
        "candidate_id"
    )
    pool = metrics[metrics["series_id"].eq("light_ruc_total_pool")].set_index(
        "candidate_id"
    )
    for candidate_id, schedule in SCHEDULES.items():
        weight_path = weights[weights["candidate_id"].eq(candidate_id)]
        rows.append(
            {
                "candidate_id": candidate_id,
                "display_name": schedule.display_name,
                "transition_completion_fy": schedule.completion_fy
                if schedule.is_structural
                else pd.NA,
                "structural_weight_fy2040": float(
                    weight_path.loc[weight_path["fy"].eq(2040), "w"].iloc[0]
                ),
                "structural_weight_fy2050": float(
                    weight_path.loc[weight_path["fy"].eq(2050), "w"].iloc[0]
                ),
                "fy2031_seam_growth_nltf": float(
                    nltf.at[candidate_id, "fy2031_seam_growth"]
                ),
                "total_nltf_fy2040": float(nltf.at[candidate_id, "fy2040"]),
                "total_nltf_fy2050": float(nltf.at[candidate_id, "fy2050"]),
                "ratio_to_official_nltf_fy2050": float(
                    nltf.at[candidate_id, "ratio_to_official_fy2050"]
                )
                if "ratio_to_official_fy2050" in nltf.columns
                else np.nan,
                "light_petrol_vkt_fy2050": float(petrol.at[candidate_id, "fy2050"]),
                "light_ruc_pool_fy2050": float(pool.at[candidate_id, "fy2050"]),
                "max_annual_growth_nltf": float(
                    nltf.at[candidate_id, "max_annual_growth"]
                ),
                "preserves_fy2030_anchor": True,
                "official_level_substituted": False,
                "lambda_used": False,
                "composition_source": "exact VFM202405 Base (production default)",
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    inputs = _pack_inputs()
    shape_vintage_id = default_long_run_shape_vintage_id(REPO_ROOT)
    bridge = load_official_vintage("BEFU26", repo_root=REPO_ROOT)
    shape = load_official_vintage(shape_vintage_id, repo_root=REPO_ROOT)
    prior = load_official_vintage("MBU26", repo_root=REPO_ROOT)
    assert bridge is not None and shape is not None and prior is not None

    weights = transition_weight_candidates_frame()
    weights.to_csv(OUT / "transition_weight_candidates.csv", index=False)
    schedule_catalogue_frame().to_csv(OUT / "transition_schedule_catalogue.csv", index=False)

    candidates = build_candidates(
        inputs, bridge.official_annual, shape.official_annual, shape_vintage_id
    )
    paths = candidate_paths_frame(candidates)
    paths.to_csv(OUT / "candidate_activity_paths.csv", index=False)
    paths[
        paths["series_id"].isin(
            [
                "net_fed_revenue",
                "total_ruc_net_revenue",
                "net_mvr_revenue",
                "tuc_net_revenue",
                "total_nltf_net_revenue",
            ]
        )
    ].to_csv(OUT / "candidate_revenue_paths.csv", index=False)

    anchors = _anchor_values(inputs)
    official_wide = shape.official_annual.pivot_table(
        index="FY", columns="series_id", values="value", aggfunc="first"
    )
    metrics = transition_metrics_frame(paths, anchors, official_wide)
    metrics.to_csv(OUT / "candidate_transition_metrics.csv", index=False)

    formula_reconciliation_frame(candidates).to_csv(
        OUT / "formula_reconciliation.csv", index=False
    )
    activity_identity_frame(
        candidates, inputs, shape.official_annual, shape_vintage_id
    ).to_csv(OUT / "activity_identity_audit.csv", index=False)
    scorecard = scorecard_frame(metrics, weights, paths)
    scorecard.to_csv(OUT / "candidate_shape_scorecard.csv", index=False)

    # Growth-index evidence, split into the three legs the method combines.
    index_frames: list[pd.DataFrame] = []
    for schedule_id in SCHEDULES:
        frame = post_model_growth_indices(
            inputs["raw_quarterly_audit"],
            inputs["scenario_input_wide"],
            scenario_name=BASE_SCENARIO,
            repo_root=REPO_ROOT,
            long_run_shape_official_annual=shape.official_annual,
            long_run_shape_vintage_id=shape_vintage_id,
            transition_schedule_id=schedule_id,
        )
        frame["candidate_id"] = schedule_id
        index_frames.append(frame)
    indices = pd.concat(index_frames, ignore_index=True)
    current_columns = ["fy", "candidate_id", "g_light_petrol_vkt", "vfm_pool_index", "g_heavy_ruc_net_km"]
    indices[current_columns].drop_duplicates().to_csv(
        OUT / "current_growth_indices.csv", index=False
    )
    indices[
        ["fy", "candidate_id", "long_run_shape_vintage_id", "s_light_petrol_vkt", "s_light_ruc_pool", "s_heavy_ruc_net_km"]
    ].to_csv(OUT / "official_growth_indices.csv", index=False)
    indices[
        ["fy", "candidate_id", "w", "h_light_petrol_vkt", "h_light_ruc_pool", "h_heavy_ruc_net_km"]
    ].to_csv(OUT / "hybrid_growth_indices.csv", index=False)

    # Anchor/shape/level decomposition for the balanced candidate.
    anchor_shape_level_audit(
        line_reconciliation=inputs["line_reconciliation"],
        raw_quarterly_audit=inputs["raw_quarterly_audit"],
        scenario_input_wide=inputs["scenario_input_wide"],
        long_run_shape_official_annual=shape.official_annual,
        long_run_shape_vintage_id=shape_vintage_id,
        transition_schedule_id="balanced_structural",
        repo_root=REPO_ROOT,
    ).to_csv(OUT / "anchor_shape_level_audit.csv", index=False)

    # Composition side by side, on the balanced candidate's hybrid pool.
    balanced = candidates["balanced_structural"]
    pool_by_fy = (
        balanced[
            balanced["scenario_name"].eq(BASE_SCENARIO)
            & balanced["series_id"].isin(POOL_CLASSES)
        ]
        .groupby("fy")["value"]
        .sum()
        .to_dict()
    )
    light_fleet_composition_audit(
        hybrid_pool_by_fy={int(fy): float(v) for fy, v in pool_by_fy.items()},
        repo_root=REPO_ROOT,
        official_shares={
            "BEFU26": shape.official_annual,
            "MBU26": prior.official_annual,
        },
    ).to_csv(OUT / "light_fleet_composition_audit.csv", index=False)

    print(scorecard.to_string(index=False))
    summary = {
        "shape_vintage_id": shape_vintage_id,
        "candidates": list(SCHEDULES),
        "production_default_unchanged": UNBLENDED_SCHEDULE_ID,
        "reported_fys": list(REPORT_FYS),
    }
    (OUT / "candidate_build_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

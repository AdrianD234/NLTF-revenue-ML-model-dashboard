from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scripts.regenerate_candidate_cone import (
    CANDIDATE_COLUMNS,
    CURRENT_FINALISTS,
    SCHIFF_MODELS,
    STREAM_TARGET_COUNTS,
    build_candidate_cone,
)


ROOT = Path(__file__).resolve().parents[1]


def _finalists() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "stream": "PED",
                "stream_label": "PED VKT per capita",
                "role": "Current finalist",
                "model": CURRENT_FINALISTS["PED"],
                "model_short": "PED vNext convex TOP2",
                "n_quarterly_pairs": 126,
                "n_origins": 11,
                "quarterly_mape": 3.131663,
                "annual_mape": 1.946846,
                "quarterly_bias_pct": 1.60759,
                "annual_bias_pct": 1.43453,
                "quarterly_p90_ape": 12.3,
                "annual_p90_ape": 4.1,
                "is_current_recommended": True,
                "is_pure_schiff": False,
                "operational_pooled_mape": 2.66414,
                "operational_horizon_mean_mape": 2.73074,
                "operational_bias_pct": 2.36071,
                "operational_annual_mape": 2.54063,
                "paper_horizon_mean_mape": 3.131663,
                "paper_pooled_mape": 4.28615,
                "paper_bias_pct": 1.60759,
                "paper_annual_mape": 1.946846,
                "paper_h09_12_mape": 7.806239,
            },
            {
                "stream": "LIGHT_RUC",
                "stream_label": "Light RUC volume",
                "role": "Current finalist",
                "model": CURRENT_FINALISTS["LIGHT_RUC"],
                "model_short": "Light RUC dynamic residual GBM W36",
                "n_quarterly_pairs": 126,
                "n_origins": 11,
                "quarterly_mape": 5.363207,
                "annual_mape": 1.273774,
                "quarterly_bias_pct": 0.83689,
                "annual_bias_pct": -1.02345,
                "quarterly_p90_ape": 15.7,
                "annual_p90_ape": 3.8,
                "is_current_recommended": True,
                "is_pure_schiff": False,
                "operational_pooled_mape": 8.272972,
                "operational_horizon_mean_mape": 6.911,
                "operational_bias_pct": 0.81,
                "operational_annual_mape": 6.77491,
                "paper_horizon_mean_mape": 5.363207,
                "paper_pooled_mape": 7.414,
                "paper_bias_pct": 0.83689,
                "paper_annual_mape": 1.273774,
                "paper_h09_12_mape": 7.806239,
            },
            {
                "stream": "HEAVY_RUC",
                "stream_label": "Heavy RUC volume",
                "role": "Current finalist",
                "model": CURRENT_FINALISTS["HEAVY_RUC"],
                "model_short": "Heavy RUC vNext convex TOP4",
                "n_quarterly_pairs": 126,
                "n_origins": 11,
                "quarterly_mape": 2.288716,
                "annual_mape": 1.682721,
                "quarterly_bias_pct": -0.11126,
                "annual_bias_pct": -0.22005,
                "quarterly_p90_ape": 11.2,
                "annual_p90_ape": 4.0,
                "is_current_recommended": True,
                "is_pure_schiff": False,
                "operational_pooled_mape": 3.01185,
                "operational_horizon_mean_mape": 2.981,
                "operational_bias_pct": -0.264,
                "operational_annual_mape": 2.31949,
                "paper_horizon_mean_mape": 2.288716,
                "paper_pooled_mape": 3.081,
                "paper_bias_pct": -0.11126,
                "paper_annual_mape": 1.682721,
                "paper_h09_12_mape": 2.095835,
            },
        ]
    )


def _schiff() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "stream": stream,
                "stream_label": label,
                "role": "Schiff specification",
                "model": SCHIFF_MODELS[stream],
                "model_short": f"{label} Schiff",
                "n_quarterly_pairs": 126,
                "n_origins": 11,
                "quarterly_mape": q,
                "annual_mape": a,
                "quarterly_bias_pct": 1.0,
                "annual_bias_pct": 0.5,
                "quarterly_p90_ape": q * 2,
                "annual_p90_ape": a * 2,
                "is_current_recommended": False,
                "is_pure_schiff": True,
                "operational_pooled_mape": oq,
                "operational_horizon_mean_mape": oq,
                "operational_bias_pct": 1.0,
                "operational_annual_mape": oa,
                "paper_horizon_mean_mape": q,
                "paper_pooled_mape": q * 0.95,
                "paper_bias_pct": 1.0,
                "paper_annual_mape": a,
                "paper_h09_12_mape": q * 1.2,
            }
            for stream, label, q, a, oq, oa in [
                ("PED", "PED VKT per capita", 4.674917, 3.585729, 4.16591, 4.0),
                ("LIGHT_RUC", "Light RUC volume", 8.521397, 2.702, 9.527168, 8.0),
                ("HEAVY_RUC", "Heavy RUC volume", 8.761652, 8.879508, 7.800196, 7.2),
            ]
        ]
    )


def _light_scorecard() -> pd.DataFrame:
    rows = []
    for i in range(180):
        rows.append(
            {
                "model": f"LIGHT_RUC_MEASURED_{i:03d}",
                "operational_n": 126,
                "operational_pooled_mape": 8.5 + i * 0.018,
                "operational_horizon_mean_mape": 7.1 + i * 0.014,
                "operational_bias_pct": 0.25,
                "operational_annual_mape": 6.9 + i * 0.01,
                "operational_h09_12_mape": 8.0 + i * 0.02,
                "paper_n": 126,
                "paper_horizon_mean_mape": 5.45 + i * 0.015,
                "paper_pooled_mape": 7.1 + i * 0.01,
                "paper_bias_pct": 0.3,
                "paper_annual_mape": 1.35 + i * 0.012,
                "paper_h09_12_mape": 7.9 + i * 0.012,
                "decision_score": i,
            }
        )
    return pd.DataFrame(rows)


@pytest.fixture()
def cone() -> pd.DataFrame:
    return build_candidate_cone(finalists=_finalists(), schiff=_schiff(), light_scorecard=_light_scorecard(), seed=1234).frame


def test_candidate_cone_builder_exact_counts_schema_and_anchors(cone: pd.DataFrame) -> None:
    assert list(cone.columns) == CANDIDATE_COLUMNS
    assert len(cone) == 400
    assert cone["stream"].value_counts().to_dict() == STREAM_TARGET_COUNTS
    for stream, model in CURRENT_FINALISTS.items():
        rows = cone[(cone["stream"].eq(stream)) & (cone["model"].eq(model))]
        assert len(rows) == 1
        assert bool(rows.iloc[0]["is_current_recommended"])
    for stream, model in SCHIFF_MODELS.items():
        rows = cone[(cone["stream"].eq(stream)) & (cone["model"].eq(model))]
        assert len(rows) == 1
        assert bool(rows.iloc[0]["is_pure_schiff"])


def test_candidate_cone_builder_repeatable() -> None:
    first = build_candidate_cone(finalists=_finalists(), schiff=_schiff(), light_scorecard=_light_scorecard(), seed=99).frame
    second = build_candidate_cone(finalists=_finalists(), schiff=_schiff(), light_scorecard=_light_scorecard(), seed=99).frame
    pd.testing.assert_frame_equal(first, second)


def test_measured_light_rows_are_not_mutated(cone: pd.DataFrame) -> None:
    measured = cone[cone["frontier_sample_class"].eq("measured_candidate")]
    assert len(measured) == 68
    source = _light_scorecard().set_index("model")
    for _, row in measured.head(20).iterrows():
        original = source.loc[row["model"]]
        assert float(row["paper_horizon_mean_mape"]) == pytest.approx(float(original["paper_horizon_mean_mape"]))
        assert float(row["paper_annual_mape"]) == pytest.approx(float(original["paper_annual_mape"]))
        assert float(row["operational_pooled_mape"]) == pytest.approx(float(original["operational_pooled_mape"]))
        assert row["frontier_sample_note"]


def test_non_anchor_rows_do_not_undercut_finalist_apex(cone: pd.DataFrame) -> None:
    for stream in STREAM_TARGET_COUNTS:
        final = cone[(cone["stream"].eq(stream)) & (cone["is_current_recommended"])].iloc[0]
        non_anchor = cone[(cone["stream"].eq(stream)) & ~cone["frontier_sample_class"].eq("anchor")]
        for column in [
            "paper_horizon_mean_mape",
            "paper_annual_mape",
            "operational_pooled_mape",
            "operational_annual_mape",
        ]:
            assert (non_anchor[column] >= final[column]).all()


def test_cone_geometry_spreads_out_from_apex(cone: pd.DataFrame) -> None:
    for stream in STREAM_TARGET_COUNTS:
        subset = cone[cone["stream"].eq(stream)].copy()
        final = subset[subset["is_current_recommended"]].iloc[0]
        subset["distance"] = (
            (subset["paper_horizon_mean_mape"] - final["paper_horizon_mean_mape"]) ** 2
            + (subset["paper_annual_mape"] - final["paper_annual_mape"]) ** 2
        ) ** 0.5
        non_anchor = subset[~subset["frontier_sample_class"].eq("anchor")]
        q10 = non_anchor["distance"].quantile(0.10)
        q90 = non_anchor["distance"].quantile(0.90)
        assert q10 < q90
        near = non_anchor[non_anchor["distance"].le(non_anchor["distance"].quantile(0.35))]
        far = non_anchor[non_anchor["distance"].ge(non_anchor["distance"].quantile(0.65))]
        assert far["paper_horizon_mean_mape"].std() > near["paper_horizon_mean_mape"].std() * 0.8


def test_regenerated_evidence_pack_cone_contract() -> None:
    cone = pd.read_parquet(ROOT / "data" / "dashboard_evidence_pack" / "data" / "candidate_cone.parquet")
    assert list(cone.columns) == CANDIDATE_COLUMNS
    assert len(cone) == 400
    assert cone["stream"].value_counts().to_dict() == STREAM_TARGET_COUNTS
    assert cone["frontier_sample_class"].value_counts().to_dict() == {
        "balanced_visual_frontier_sample": 326,
        "measured_candidate": 68,
        "anchor": 6,
    }
    for stream, model in CURRENT_FINALISTS.items():
        rows = cone[(cone["stream"].eq(stream)) & (cone["model"].eq(model))]
        assert len(rows) == 1
        assert bool(rows.iloc[0]["is_current_recommended"])
    metrics = ["quarterly_mape", "annual_mape", "operational_pooled_mape", "operational_annual_mape"]
    assert cone[metrics].notna().all().all()
    assert (cone[metrics].astype(float) > 0).all().all()
    for stream in STREAM_TARGET_COUNTS:
        final = cone[(cone["stream"].eq(stream)) & (cone["is_current_recommended"])].iloc[0]
        non_anchor = cone[(cone["stream"].eq(stream)) & ~cone["frontier_sample_class"].eq("anchor")]
        for column in [
            "paper_horizon_mean_mape",
            "paper_annual_mape",
            "operational_pooled_mape",
            "operational_annual_mape",
        ]:
            assert (non_anchor[column] >= final[column]).all()

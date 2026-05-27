from __future__ import annotations

import pandas as pd

from model_dashboard.labels import model_hover_description, model_hover_title
from model_dashboard.plots import plot_candidate_landscape, plot_ensemble_composition


HEAVY_ELASTIC = "HEAVY_RUC__dynamic_no_leads__Elastic_alpha0_005_l1_ratio0_2__ylag__w64"
LIGHT_RESID_GBM = "dynamic_RESID_GBR_n150_d1_lr0.05_w36"


def test_heavy_elastic_tooltip_is_management_friendly() -> None:
    title = model_hover_title(HEAVY_ELASTIC)
    detail = model_hover_description(HEAVY_ELASTIC, weight=0.469332)

    assert title == "Dynamic ElasticNet model"
    assert "Uses no lead variables" in detail
    assert "includes target lags" in detail
    assert "64-quarter rolling window" in detail
    assert "alpha = 0.005" in detail
    assert "L1 ratio = 0.2" in detail
    assert "Ensemble weight: 46.9%." in detail
    assert "__" not in detail
    assert "Alpha0 005" not in detail


def test_light_ruc_residual_gbm_tooltip_is_management_friendly() -> None:
    title = model_hover_title(LIGHT_RESID_GBM)
    detail = model_hover_description(LIGHT_RESID_GBM)

    assert title == "Dynamic residual GBM"
    assert "two-stage model" in detail
    assert "base economic model" in detail
    assert "shallow gradient-boosted residual correction" in detail
    assert "150 trees" in detail
    assert "depth 1" in detail
    assert "learning rate 0.05" in detail
    assert "36-quarter rolling window" in detail
    assert "_" not in detail


def test_candidate_frontier_hover_uses_model_detail_not_raw_identifier() -> None:
    data = pd.DataFrame(
        [
            {
                "stream_label": "Heavy RUC volume",
                "model": HEAVY_ELASTIC,
                "quarterly_mape": 3.48,
                "annual_mape": 3.02,
                "candidate_role": "Candidate",
                "is_distribution_sample": True,
                "is_current_recommended": False,
                "is_pure_schiff": False,
            }
        ]
    )

    fig = plot_candidate_landscape(data)
    customdata = fig.data[0].customdata[0]

    assert "Dynamic ElasticNet model" in customdata
    assert any("Uses no lead variables" in str(value) for value in customdata)
    assert not any(HEAVY_ELASTIC in str(value) for value in customdata)
    assert "Full model" not in str(fig.data[0].hovertemplate)
    assert "Model detail" in str(fig.data[0].hovertemplate)


def test_ensemble_hover_includes_component_detail_and_weight() -> None:
    weights = pd.DataFrame(
        [
            {
                "stream_label": "Heavy RUC volume",
                "ensemble": "HEAVY_RUC__RECON_STATIC_REBUILT",
                "component_model": HEAVY_ELASTIC,
                "weight": 0.469332,
            }
        ]
    )

    fig, _ = plot_ensemble_composition(weights)
    customdata = fig.data[0].customdata[0]

    assert "Dynamic ElasticNet model" in customdata
    assert any("Ensemble weight: 46.9%." in str(value) for value in customdata)
    assert not any(HEAVY_ELASTIC in str(value) for value in customdata)
    assert "Full component" not in str(fig.data[0].hovertemplate)
    assert "Component detail" in str(fig.data[0].hovertemplate)

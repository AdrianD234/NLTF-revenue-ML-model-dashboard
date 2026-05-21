from __future__ import annotations

import pandas as pd

from model_dashboard.labels import is_schiff_text
from model_dashboard.metrics import (
    filter_to_model_keys,
    model_key_series,
    model_key_set,
    bias,
    horizon_bucket,
    june_year,
    mape,
    p90_ape,
    row_key,
)


def test_mape_calculation() -> None:
    actual = pd.Series([100.0, 200.0])
    pred = pd.Series([110.0, 180.0])

    assert mape(actual, pred) == 10.0


def test_bias_calculation() -> None:
    actual = pd.Series([100.0, 200.0])
    pred = pd.Series([110.0, 180.0])

    assert bias(actual, pred) == 0.0


def test_p90_ape_calculation() -> None:
    actual = pd.Series([100.0, 100.0, 100.0])
    pred = pd.Series([101.0, 105.0, 120.0])

    assert round(p90_ape(actual, pred), 2) == 17.0


def test_horizon_bucket_assignment() -> None:
    assert horizon_bucket(1) == "1-4 qtrs"
    assert horizon_bucket(5) == "5-8 qtrs"
    assert horizon_bucket(12) == "9-12 qtrs"
    assert horizon_bucket(13) == "Other"


def test_june_year_conversion() -> None:
    assert june_year("2025Q1") == 2025
    assert june_year("2025Q2") == 2025
    assert june_year("2025Q3") == 2026
    assert june_year("2025Q4") == 2026


def test_schiff_classifier_distinguishes_benchmark_from_challengers() -> None:
    assert is_schiff_text(
        "LIGHT_RUC__policy_dynamic_no_leads__SCHIFF_OLS_W52",
        "bespoke_schiff",
        "policy_dynamic_no_leads",
    )
    assert not is_schiff_text(
        "LIGHT_RUC__policy_dynamic_rich__SCHIFF_RESID_HUBER_alpha_0_0001",
        "bespoke_residual_correction",
        "policy_dynamic_rich",
    )
    assert not is_schiff_text(
        "LIGHT_RUC__final__fixedblend_schiff0.20_policy_dynamic_no_leads_schiff_ols_w52",
        "posthoc_ensemble",
        "posthoc_ensemble",
    )


def test_vectorized_model_keys_match_legacy_row_keys() -> None:
    frame = pd.DataFrame(
        [
            {"stage": "final", "stream": "PED", "variant": "v1", "model": "m1"},
            {"stage": " final ", "stream": "LIGHT_RUC", "variant": "nan", "model": "m2"},
            {"stage": "screen", "stream": "HEAVY_RUC", "variant": "v3", "model": "m3"},
        ]
    )

    legacy = {"\x1f".join(row_key(row)) for _, row in frame.iterrows()}
    assert set(model_key_series(frame)) == legacy


def test_filter_to_model_keys_uses_vectorized_membership() -> None:
    frame = pd.DataFrame(
        [
            {"stage": "final", "stream": "PED", "variant": "v1", "model": "m1", "value": 1},
            {"stage": "final", "stream": "PED", "variant": "v1", "model": "m1", "value": 2},
            {"stage": "final", "stream": "PED", "variant": "v1", "model": "m2", "value": 3},
        ]
    )
    finalist = frame.iloc[[0]].copy()

    filtered = filter_to_model_keys(frame, model_key_set(finalist))

    assert filtered["value"].tolist() == [1, 2]

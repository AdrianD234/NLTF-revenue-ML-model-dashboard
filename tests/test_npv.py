from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from model_dashboard.npv import (
    MBCM_RATE_AFTER,
    MBCM_RATE_FIRST,
    MBCM_SWITCH_YEAR,
    average_annual,
    cumulative_total,
    horizon_label,
    mbcm_discount_factors,
    npv_to_horizon,
    single_rate_discount_factors,
)


def test_mbcm_factors_anchor_and_first_year() -> None:
    factors = mbcm_discount_factors(3)
    assert factors[0] == pytest.approx(1.0)
    assert factors[1] == pytest.approx(1 / 1.02)
    assert factors[2] == pytest.approx(1 / 1.02**2)


def test_mbcm_piecewise_leg_switches_to_lower_rate() -> None:
    factors = mbcm_discount_factors(MBCM_SWITCH_YEAR + 3)
    at_switch = 1 / (1 + MBCM_RATE_FIRST) ** MBCM_SWITCH_YEAR
    assert factors[MBCM_SWITCH_YEAR] == pytest.approx(at_switch)
    assert factors[MBCM_SWITCH_YEAR + 1] == pytest.approx(at_switch / (1 + MBCM_RATE_AFTER))
    assert factors[MBCM_SWITCH_YEAR + 2] == pytest.approx(at_switch / (1 + MBCM_RATE_AFTER) ** 2)


def test_constant_stream_npv_matches_closed_form_annuity() -> None:
    years = list(range(2026, 2051))  # 25 payments, first at t=0
    stream = pd.Series(100.0, index=years)
    npv = npv_to_horizon(stream)
    r = MBCM_RATE_FIRST
    # annuity-due style: payment at t=0..24 -> 100 * (1 - (1+r)^-25)/r * (1+r)
    closed_form = 100.0 * (1 - (1 + r) ** -25) / r * (1 + r)
    assert npv == pytest.approx(closed_form, rel=1e-12)


def test_single_rate_override() -> None:
    years = [2026, 2027, 2028]
    stream = pd.Series([100.0, 100.0, 100.0], index=years)
    npv = npv_to_horizon(stream, rate=0.05)
    manual = 100.0 + 100.0 / 1.05 + 100.0 / 1.05**2
    assert npv == pytest.approx(manual)
    factors = single_rate_discount_factors(3, 0.05)
    assert factors[2] == pytest.approx(1 / 1.05**2)


def test_pre_anchor_years_and_nans_are_excluded() -> None:
    stream = pd.Series([999.0, 100.0, np.nan, 100.0], index=[2024, 2026, 2027, 2028])
    npv = npv_to_horizon(stream)
    assert npv == pytest.approx(100.0 + 100.0 / 1.02**2)


def test_cumulative_average_and_label() -> None:
    stream = pd.Series([10.0, 20.0, 30.0], index=[2026, 2027, 2028])
    assert cumulative_total(stream) == pytest.approx(60.0)
    assert average_annual(stream) == pytest.approx(20.0)
    assert horizon_label(stream) == "FY2026–FY2028 (3 years)"

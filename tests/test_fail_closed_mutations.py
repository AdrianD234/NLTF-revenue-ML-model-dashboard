"""Fault injection: prove the contracts fail on broken data, not just clean data.

A completeness check that only ever sees a healthy pack proves nothing. Each
test here deliberately damages one cell and requires the specific structured
failure, and the H21+ case requires the opposite - that a deliberately withheld
row is never reported as missing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from model_dashboard.completeness_contract import (
    CompletenessContractError,
    evaluate_cell,
)

REQUIRED = dict(
    scenario="current_basecase",
    role="basecase",
    stage="S4",
    time_grain="june_year",
    period="FY2027",
    series="light_ruc_net_km",
)
GOOD = pd.Series([12_752.374])
GOOD_UNIT = pd.Series(["million km"])


def _evaluate(**overrides):
    kwargs = {**REQUIRED, "values": GOOD, "units": GOOD_UNIT, **overrides}
    return evaluate_cell(**kwargs)


def test_healthy_cell_is_available() -> None:
    record = _evaluate()
    assert record.status == "required_and_available"
    assert not record.is_failure
    assert record.actual_unit == "million_km"


# 1, 2 -----------------------------------------------------------------------
@pytest.mark.parametrize(
    ("period", "series"),
    [("FY2026", "light_ruc_net_km"), ("FY2030", "total_nltf_net_revenue")],
)
def test_removing_a_required_current_row_fails_closed(period, series) -> None:
    record = _evaluate(period=period, series=series, values=None, units=None)
    assert record.status == "missing_derived_output"
    assert record.is_failure
    with pytest.raises(CompletenessContractError) as caught:
        _evaluate(period=period, series=series, values=None, units=None, raise_on_failure=True)
    message = str(caught.value)
    assert series in message and period in message and "basecase" in message


def test_removing_a_required_h20_quarter_fails_closed() -> None:
    record = evaluate_cell(
        scenario="current_basecase", role="basecase", stage="S0",
        time_grain="quarterly", period="2030Q4", series="light_ruc_net_km",
        values=None, units=None,
    )
    assert record.horizon_state == "within_h20"
    assert record.status == "missing_derived_output"


# 3 --------------------------------------------------------------------------
def test_removing_an_official_row_inside_fy2055_fails_closed() -> None:
    record = evaluate_cell(
        scenario="mbu26_official", role="official_comparator", stage="S4",
        time_grain="june_year", period="FY2049", series="total_nltf_net_revenue",
        values=None, units=None,
    )
    assert record.status == "missing_derived_output"
    assert record.horizon_state == "official_source_horizon"


# 4 --------------------------------------------------------------------------
def test_duplicate_rows_with_different_values_fail_closed() -> None:
    record = _evaluate(values=pd.Series([12_752.374, 99_999.0]), units=pd.Series(["million km"] * 2))
    assert record.status == "duplicate_or_ambiguous"
    assert "arbitrary" in record.reason


def test_duplicate_rows_agreeing_exactly_are_not_a_failure() -> None:
    record = _evaluate(values=pd.Series([12_752.374] * 2), units=pd.Series(["million km"] * 2))
    assert record.status == "required_and_available"


# 5, 6 -----------------------------------------------------------------------
def test_unknown_unit_fails_closed() -> None:
    record = _evaluate(units=pd.Series(["furlongs"]))
    assert record.status == "unit_invalid"
    assert "furlongs" in record.reason


def test_dimensionally_incompatible_unit_fails_closed() -> None:
    record = _evaluate(units=pd.Series(["$m nominal ex GST"]))
    assert record.status == "unit_invalid"
    assert "million_km" in record.reason


# 7, 8 -----------------------------------------------------------------------
def test_nan_value_fails_closed() -> None:
    assert _evaluate(values=pd.Series([np.nan])).status == "non_numeric"


def test_infinite_value_fails_closed() -> None:
    assert _evaluate(values=pd.Series([np.inf])).status == "non_finite"


def test_non_numeric_text_fails_closed() -> None:
    assert _evaluate(values=pd.Series(["unavailable"])).status == "non_numeric"


# 14 -------------------------------------------------------------------------
@pytest.mark.parametrize("period", ["2031Q1", "2031Q2"])
def test_withheld_h21_quarter_is_not_reported_missing(period) -> None:
    record = evaluate_cell(
        scenario="current_basecase", role="basecase", stage="S4",
        time_grain="quarterly", period=period, series="light_ruc_net_km",
        values=None, units=None,
    )
    assert record.status == "intentionally_unavailable_h21_plus"
    assert not record.is_failure
    assert record.horizon_state == "beyond_h20"


def test_withheld_fy2031_annual_is_not_reported_missing() -> None:
    record = _evaluate(period="FY2031", values=None, units=None)
    assert record.status == "intentionally_unavailable_h21_plus"
    assert not record.is_failure


def test_a_value_appearing_beyond_the_horizon_is_itself_a_failure() -> None:
    """The withheld rule cuts both ways: H21+ must not carry a live value."""
    record = _evaluate(period="FY2031")
    assert record.status == "formula_invalid"
    assert record.is_failure


# raw audit ------------------------------------------------------------------
def test_raw_audit_evidence_cannot_satisfy_a_decision_facing_requirement() -> None:
    audit = _evaluate(period="FY2031", decision_facing=False)
    assert audit.status == "optional_and_available"
    assert not audit.decision_facing
    required = _evaluate(period="FY2031", values=None, units=None)
    assert required.status == "intentionally_unavailable_h21_plus"
    # The audit row exists, yet the decision-facing cell is still not available.
    assert required.status != "required_and_available"


def test_no_failure_status_is_silently_swallowed() -> None:
    """Every failure status must raise when the caller asks it to."""
    from model_dashboard.completeness_contract import _FAILURE_STATUSES

    cases = {
        "missing_derived_output": dict(values=None, units=None),
        "duplicate_or_ambiguous": dict(values=pd.Series([1.0, 2.0]), units=pd.Series(["million km"] * 2)),
        "non_numeric": dict(values=pd.Series([np.nan])),
        "non_finite": dict(values=pd.Series([np.inf])),
        "unit_invalid": dict(units=pd.Series(["furlongs"])),
    }
    for status, overrides in cases.items():
        assert _evaluate(**overrides).status == status
        with pytest.raises(CompletenessContractError):
            _evaluate(**overrides, raise_on_failure=True)
    assert set(cases) <= set(_FAILURE_STATUSES)

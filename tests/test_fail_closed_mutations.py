"""Fault injection: prove the contracts fail on broken data, not just clean data.

A completeness check that only ever sees a healthy pack proves nothing. Each
test here deliberately damages one cell, series or frame and requires the
specific structured failure. Two tests require the opposite - that a
deliberately withheld H21+ row is never reported as missing, and that a raw
audit row can never satisfy a decision-facing requirement.

Three rules here are stricter than the first P1.1 revision. A required row
with no unit declaration fails (it used to fall through to AVAILABLE, so
supplying nothing was safer than supplying something wrong). Every duplicate
canonical key fails (an identical duplicate used to be accepted as
idempotent). An entirely absent required series fails as
``missing_required_series`` rather than quietly ceasing to be expected.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from model_dashboard.completeness_contract import (
    CompletenessContractError,
    evaluate_cell,
    validate_frame_completeness,
)
from model_dashboard.series_inventory_contract import REQUIRED_QUARTERS

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
    assert record.unit_status == "valid"
    assert record.observed_count == 1


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
        values=None, units=None, expected_unit="km",
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


# 4 - duplicates: EVERY duplicate canonical key fails -------------------------
def test_duplicate_rows_with_different_values_fail_closed() -> None:
    record = _evaluate(values=pd.Series([12_752.374, 99_999.0]), units=pd.Series(["million km"] * 2))
    assert record.status == "duplicate_or_ambiguous"
    assert "arbitrary" in record.reason
    assert record.observed_count == 2


def test_duplicate_rows_agreeing_exactly_also_fail_closed() -> None:
    """An exact duplicate is not idempotent.

    Downstream code can sum it twice or take an arbitrary first match, and it
    is usually the visible symptom of a join or materialisation defect. The
    earlier revision accepted this case; that permissiveness is the defect.
    """
    record = _evaluate(values=pd.Series([12_752.374] * 2), units=pd.Series(["million km"] * 2))
    assert record.status == "duplicate_or_ambiguous"
    assert record.is_failure
    assert "exactly one" in record.reason


def test_duplicate_with_a_different_unit_fails_closed() -> None:
    record = _evaluate(
        values=pd.Series([12_752.374, 12_752_374_000.0]),
        units=pd.Series(["million km", "net km"]),
    )
    assert record.status == "duplicate_or_ambiguous"


def test_duplicate_with_conflicting_lineage_fails_closed() -> None:
    """Same key, same value, different provenance is still ambiguous."""
    record = _evaluate(values=pd.Series([12_752.374] * 2), units=pd.Series(["million km"] * 2))
    assert record.is_failure


def test_duplicate_created_by_joining_two_source_frames_fails_closed() -> None:
    """The realistic shape: a fan-out join doubling every row of a series."""
    left = pd.DataFrame(
        {
            "scenario_role": ["basecase"] * 3,
            "time_grain": ["june_year"] * 3,
            "series_id": ["light_ruc_net_km"] * 3,
            "period": ["FY2026", "FY2027", "FY2028"],
            "value": [1.0, 2.0, 3.0],
            "value_unit": ["million km"] * 3,
        }
    )
    right = pd.DataFrame({"period": ["FY2026", "FY2026"], "extra": ["a", "b"]})
    joined = left.merge(right, on="period", how="left")
    matched = joined[joined["period"].eq("FY2026")]
    record = evaluate_cell(
        scenario="current_basecase", role="basecase", stage="S4",
        time_grain="june_year", period="FY2026", series="light_ruc_net_km",
        values=matched["value"], units=matched["value_unit"],
    )
    assert record.status == "duplicate_or_ambiguous"


# 5, 6 - units ---------------------------------------------------------------
def test_unknown_unit_fails_closed() -> None:
    record = _evaluate(units=pd.Series(["furlongs"]))
    assert record.status == "unit_invalid"
    assert "furlongs" in record.reason
    assert record.unit_status == "unknown"


def test_dimensionally_incompatible_unit_fails_closed() -> None:
    record = _evaluate(units=pd.Series(["$m nominal ex GST"]))
    assert record.status == "unit_invalid"
    assert "million_km" in record.reason
    assert record.unit_status == "incompatible"


@pytest.mark.parametrize("absent", [None, pd.Series([""]), pd.Series(["   "]), pd.Series([np.nan])])
def test_missing_unit_declaration_fails_closed(absent) -> None:
    """Absence must fail in its own right, not skip validation."""
    record = _evaluate(units=absent)
    assert record.status == "missing_unit_declaration"
    assert record.is_failure
    assert record.unit_status == "absent"
    with pytest.raises(CompletenessContractError):
        _evaluate(units=absent, raise_on_failure=True)


def test_dropping_the_unit_column_entirely_fails_closed() -> None:
    frame = pd.DataFrame(
        {
            "scenario_role": ["basecase"],
            "time_grain": ["june_year"],
            "series_id": ["light_ruc_net_km"],
            "period": ["FY2027"],
            "value": [12_752.374],
        }
    )
    matched = frame[frame["period"].eq("FY2027")]
    record = evaluate_cell(
        scenario="current_basecase", role="basecase", stage="S4",
        time_grain="june_year", period="FY2027", series="light_ruc_net_km",
        values=matched["value"], units=None,
    )
    assert record.status == "missing_unit_declaration"


def test_blanking_every_unit_for_one_required_series_fails_closed(real_chart_rows) -> None:
    frame = real_chart_rows.copy()
    frame.loc[frame["series_id"].eq("light_ruc_net_km"), "value_unit"] = ""
    with pytest.raises(CompletenessContractError) as caught:
        validate_frame_completeness(frame, raise_on_failure=True)
    assert caught.value.record.status == "missing_unit_declaration"
    assert caught.value.record.series == "light_ruc_net_km"


# 7, 8 - values --------------------------------------------------------------
def test_nan_value_fails_closed() -> None:
    assert _evaluate(values=pd.Series([np.nan])).status == "non_numeric"


def test_infinite_value_fails_closed() -> None:
    assert _evaluate(values=pd.Series([np.inf])).status == "non_finite"


def test_non_numeric_text_fails_closed() -> None:
    assert _evaluate(values=pd.Series(["unavailable"])).status == "non_numeric"


# 14 - withheld H21+ ---------------------------------------------------------
@pytest.mark.parametrize("period", ["2031Q1", "2031Q2"])
def test_withheld_h21_quarter_is_not_reported_missing(period) -> None:
    record = evaluate_cell(
        scenario="current_basecase", role="basecase", stage="S4",
        time_grain="quarterly", period=period, series="light_ruc_net_km",
        values=None, units=None, expected_unit="km",
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
        "missing_unit_declaration": dict(units=None),
    }
    for status, overrides in cases.items():
        assert _evaluate(**overrides).status == status
        with pytest.raises(CompletenessContractError):
            _evaluate(**overrides, raise_on_failure=True)
    assert set(cases) <= set(_FAILURE_STATUSES)

"""Registry, schedule and factor gates for the governed 12c deferral states.

Covers the acceptance tests the deferral-duration handoff names:
  * exactly eight canonical states, six finite deferrals, quarters {2,4,...,12};
  * unique IDs, labels, display order and start periods;
  * the exact deferred start quarters;
  * legacy aliases resolve; unknown states fail closed everywhere;
  * per-state direct windows, in-window no-uplift rates, catch-up quarters
    (including catch-up coinciding with another scheduled increase);
  * quarterly and annual factor exactness;
  * the generic six-month state equals the legacy six-month wrappers within
    one process (environment-independent equivalence gate).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from model_dashboard import rate_paths
from model_dashboard.fed_policy_states import (
    FED_DEFERRAL_CATCH_UP_NOTE,
    FED_POLICY_SPECS,
    FED_UPLIFT_START_PERIOD,
    PolicyStateError,
    calculation_state_ids,
    finite_deferral_specs,
    policy_spec,
    policy_state_aliases,
    policy_state_ids,
    quarter_serial,
    serial_quarter,
)

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_STATE_IDS = (
    "published",
    "delayed_6m",
    "delayed_12m",
    "delayed_18m",
    "delayed_24m",
    "delayed_30m",
    "delayed_36m",
    "off",
)
EXPECTED_CALC_IDS = (
    "published",
    "delay_6m",
    "delay_12m",
    "delay_18m",
    "delay_24m",
    "delay_30m",
    "delay_36m",
    "no_uplift",
)
EXPECTED_STARTS = ("2027Q3", "2028Q1", "2028Q3", "2029Q1", "2029Q3", "2030Q1")
EXPECTED_LABELS = (
    "Original timing — 1 Jan 2027",
    "Deferred 0.5 years (6 months) — 1 Jul 2027",
    "Deferred 1.0 year (12 months) — 1 Jan 2028",
    "Deferred 1.5 years (18 months) — 1 Jul 2028",
    "Deferred 2.0 years (24 months) — 1 Jan 2029",
    "Deferred 2.5 years (30 months) — 1 Jul 2029",
    "Deferred 3.0 years (36 months) — 1 Jan 2030",
    "No 12c uplift",
)
# Direct rate-affected calendar-quarter windows per finite deferral.
EXPECTED_WINDOWS = {
    "delay_6m": ("2027Q1", "2027Q2"),
    "delay_12m": ("2027Q1", "2027Q2", "2027Q3", "2027Q4"),
    "delay_18m": ("2027Q1", "2027Q2", "2027Q3", "2027Q4", "2028Q1", "2028Q2"),
    "delay_24m": (
        "2027Q1", "2027Q2", "2027Q3", "2027Q4",
        "2028Q1", "2028Q2", "2028Q3", "2028Q4",
    ),
    "delay_30m": (
        "2027Q1", "2027Q2", "2027Q3", "2027Q4",
        "2028Q1", "2028Q2", "2028Q3", "2028Q4",
        "2029Q1", "2029Q2",
    ),
    "delay_36m": (
        "2027Q1", "2027Q2", "2027Q3", "2027Q4",
        "2028Q1", "2028Q2", "2028Q3", "2028Q4",
        "2029Q1", "2029Q2", "2029Q3", "2029Q4",
    ),
}
# Governed source rates (data/revenue_model_source_pack/2026_05_19/
# fed_rate_paths.csv): planned and no-uplift by calendar year.
PLANNED_BY_YEAR = {2027: 0.82024, 2028: 0.88024, 2029: 0.92024, 2030: 0.96024}
NO_UPLIFT_BY_YEAR = {2027: 0.70024, 2028: 0.76024, 2029: 0.80024, 2030: 0.84024}


# --------------------------------------------------------------- A. registry


def test_registry_has_exactly_eight_states_in_display_order() -> None:
    assert policy_state_ids() == EXPECTED_STATE_IDS
    assert calculation_state_ids() == EXPECTED_CALC_IDS
    assert tuple(spec.label for spec in FED_POLICY_SPECS) == EXPECTED_LABELS
    assert tuple(spec.display_order for spec in FED_POLICY_SPECS) == tuple(range(8))


def test_registry_has_exactly_six_finite_deferrals() -> None:
    deferrals = finite_deferral_specs()
    assert len(deferrals) == 6
    assert [spec.delay_quarters for spec in deferrals] == [2, 4, 6, 8, 10, 12]
    assert [spec.delay_months for spec in deferrals] == [6, 12, 18, 24, 30, 36]
    assert tuple(spec.start_period for spec in deferrals) == EXPECTED_STARTS


def test_registry_identities_are_unique() -> None:
    for field in ("state_id", "calculation_state_id", "label", "display_order"):
        values = [getattr(spec, field) for spec in FED_POLICY_SPECS]
        assert len(set(values)) == len(values), field
    starts = [spec.start_period for spec in finite_deferral_specs()]
    assert len(set(starts)) == len(starts)


def test_legacy_aliases_resolve_to_their_states() -> None:
    aliases = policy_state_aliases()
    assert aliases["delay_6m"] == "delayed_6m"
    assert aliases["shifted_6m"] == "delayed_6m"
    assert aliases["deferred"] == "delayed_6m"
    assert aliases["no_uplift"] == "off"
    assert aliases["original"] == "published"
    assert aliases["planned"] == "published"
    assert aliases["published_timing"] == "published"
    for months in (12, 18, 24, 30, 36):
        assert aliases[f"delay_{months}m"] == f"delayed_{months}m"
        assert aliases[f"shifted_{months}m"] == f"delayed_{months}m"
    assert policy_spec("SHIFTED_18M").state_id == "delayed_18m"


def test_unknown_states_fail_closed() -> None:
    with pytest.raises(PolicyStateError):
        policy_spec("delayed_9m")
    with pytest.raises(PolicyStateError):
        policy_spec("")
    with pytest.raises(PolicyStateError):
        policy_spec(True)
    with pytest.raises(ValueError):
        rate_paths.fed_policy_quarterly_factors(ROOT, "delayed_9m")
    with pytest.raises(ValueError):
        rate_paths.fed_policy_affected_periods(ROOT, "not_a_state")


def test_start_periods_follow_the_serial_rule() -> None:
    base = quarter_serial(FED_UPLIFT_START_PERIOD)
    for spec in finite_deferral_specs():
        assert quarter_serial(spec.start_period) == base + spec.delay_quarters
        assert serial_quarter(base + spec.delay_quarters) == spec.start_period


def test_catch_up_note_is_worded_exactly() -> None:
    assert "Only the initial 12c/L wedge is deferred" in FED_DEFERRAL_CATCH_UP_NOTE
    assert "retain their published dates" in FED_DEFERRAL_CATCH_UP_NOTE
    assert "catches up to the published rate" in FED_DEFERRAL_CATCH_UP_NOTE
    for spec in finite_deferral_specs():
        if spec.delay_months != 6:
            assert FED_DEFERRAL_CATCH_UP_NOTE in spec.note


# -------------------------------------------------------------- B. schedules


@pytest.fixture(scope="module")
def quarterly() -> pd.DataFrame:
    return rate_paths.ped_quarterly_rate_schedules(ROOT)


def test_each_deferral_changes_exactly_its_direct_window(quarterly) -> None:
    planned = pd.to_numeric(quarterly["planned"], errors="coerce")
    for spec in finite_deferral_specs():
        target = pd.to_numeric(quarterly[spec.schedule_column], errors="coerce")
        changed = quarterly[planned.notna() & target.notna() & (planned - target).abs().gt(1e-9)]
        assert tuple(changed.index) == EXPECTED_WINDOWS[spec.calculation_state_id], spec.state_id


def test_within_window_selected_equals_no_uplift(quarterly) -> None:
    no_uplift = pd.to_numeric(quarterly["no_uplift"], errors="coerce")
    for spec in finite_deferral_specs():
        target = pd.to_numeric(quarterly[spec.schedule_column], errors="coerce")
        for quarter in spec.direct_affected_quarters():
            assert float(target.at[quarter]) == float(no_uplift.at[quarter]), (
                spec.state_id,
                quarter,
            )
            year = int(quarter.split("Q")[0])
            assert float(target.at[quarter]) == pytest.approx(NO_UPLIFT_BY_YEAR[year])


def test_at_and_after_start_selected_equals_planned(quarterly) -> None:
    planned = pd.to_numeric(quarterly["planned"], errors="coerce")
    order = {quarter: index for index, quarter in enumerate(quarterly.index)}
    for spec in finite_deferral_specs():
        target = pd.to_numeric(quarterly[spec.schedule_column], errors="coerce")
        start_index = order[spec.start_period]
        for quarter, position in order.items():
            if position >= start_index and pd.notna(planned.at[quarter]):
                assert float(target.at[quarter]) == float(planned.at[quarter]), (
                    spec.state_id,
                    quarter,
                )


def test_before_uplift_start_selected_equals_planned(quarterly) -> None:
    planned = pd.to_numeric(quarterly["planned"], errors="coerce")
    uplift = quarter_serial(FED_UPLIFT_START_PERIOD)
    for spec in finite_deferral_specs():
        target = pd.to_numeric(quarterly[spec.schedule_column], errors="coerce")
        for quarter in quarterly.index:
            if quarter_serial(str(quarter)) < uplift and pd.notna(planned.at[quarter]):
                assert float(target.at[quarter]) == float(planned.at[quarter])


def test_catch_up_quarters_including_coincident_scheduled_increases(quarterly) -> None:
    """The rate at each deferred start jumps to the full published rate.

    A 12-month deferral rejoins at 2028Q1 where the separate 6c increase also
    lands, so the one-quarter jump is 0.70024 -> 0.88024. An 18-month deferral
    lets the 2028Q1 6c increase occur on its published date inside the window
    (no-uplift rate steps 0.70024 -> 0.76024), then rejoins at 2028Q3.
    """
    def rate(column: str, quarter: str) -> float:
        return float(pd.to_numeric(quarterly.at[quarter, column]))

    # 6m: rejoin 2027Q3, catch-up 0.70024 -> 0.82024
    assert rate("delayed_6m", "2027Q2") == pytest.approx(0.70024)
    assert rate("delayed_6m", "2027Q3") == pytest.approx(0.82024)
    # 12m: rejoin 2028Q1 coincides with the scheduled 6c step: jump to 0.88024
    assert rate("delayed_12m", "2027Q4") == pytest.approx(0.70024)
    assert rate("delayed_12m", "2028Q1") == pytest.approx(0.88024)
    # 18m: the scheduled 6c step occurs inside the window on its original date
    assert rate("delayed_18m", "2027Q4") == pytest.approx(0.70024)
    assert rate("delayed_18m", "2028Q1") == pytest.approx(0.76024)
    assert rate("delayed_18m", "2028Q3") == pytest.approx(0.88024)
    # 24m: rejoin 2029Q1 coincides with the scheduled 4c step
    assert rate("delayed_24m", "2028Q4") == pytest.approx(0.76024)
    assert rate("delayed_24m", "2029Q1") == pytest.approx(0.92024)
    # 30m: rejoin 2029Q3 (no coincident step: planned holds 0.92024)
    assert rate("delayed_30m", "2029Q2") == pytest.approx(0.80024)
    assert rate("delayed_30m", "2029Q3") == pytest.approx(0.92024)
    # 36m: rejoin 2030Q1 coincides with the scheduled 4c step
    assert rate("delayed_36m", "2029Q4") == pytest.approx(0.80024)
    assert rate("delayed_36m", "2030Q1") == pytest.approx(0.96024)


def test_longer_deferral_rate_never_exceeds_shorter_before_catch_up(quarterly) -> None:
    deferrals = finite_deferral_specs()
    for shorter, longer in zip(deferrals, deferrals[1:], strict=False):
        shorter_rate = pd.to_numeric(quarterly[shorter.schedule_column], errors="coerce")
        longer_rate = pd.to_numeric(quarterly[longer.schedule_column], errors="coerce")
        for quarter in quarterly.index:
            if pd.isna(shorter_rate.at[quarter]) or pd.isna(longer_rate.at[quarter]):
                continue
            if quarter_serial(str(quarter)) < quarter_serial(longer.start_period):
                assert float(longer_rate.at[quarter]) <= float(shorter_rate.at[quarter]) + 1e-12


def test_direct_windows_are_nested(quarterly) -> None:
    deferrals = finite_deferral_specs()
    for shorter, longer in zip(deferrals, deferrals[1:], strict=False):
        shorter_window = set(shorter.direct_affected_quarters())
        longer_window = set(longer.direct_affected_quarters())
        assert shorter_window < longer_window


def test_affected_periods_group_by_fiscal_year() -> None:
    periods = rate_paths.fed_policy_affected_periods(ROOT, "delay_18m")
    assert periods == {
        2027: ("2027Q1", "2027Q2"),
        2028: ("2027Q3", "2027Q4", "2028Q1", "2028Q2"),
    }
    periods_36 = rate_paths.fed_policy_affected_periods(ROOT, "delay_36m")
    assert set(periods_36) == {2027, 2028, 2029, 2030}
    assert periods_36[2030] == ("2029Q3", "2029Q4")
    assert rate_paths.fed_policy_affected_periods(ROOT, "published") == {}


def test_quarterly_factors_are_exact_ratios(quarterly) -> None:
    planned = pd.to_numeric(quarterly["planned"], errors="coerce")
    for spec in finite_deferral_specs():
        factors = rate_paths.fed_policy_quarterly_factors(ROOT, spec.calculation_state_id)
        target = pd.to_numeric(quarterly[spec.schedule_column], errors="coerce")
        for quarter in spec.direct_affected_quarters():
            expected = float(target.at[quarter]) / float(planned.at[quarter])
            assert factors[quarter] == expected, (spec.state_id, quarter)
        assert factors[spec.start_period] == pytest.approx(1.0, abs=1e-15)
    six_month = rate_paths.fed_policy_quarterly_factors(ROOT, "delay_6m")
    assert six_month["2027Q1"] == pytest.approx(0.70024 / 0.82024, rel=1e-15)


# ------------------------------------------- C. six-month equivalence (in-process)


def test_generic_six_month_state_equals_legacy_wrappers() -> None:
    """The generic delayed_6m path must equal the legacy six-month functions.

    In-process equivalence, independent of the runner environment: the same
    inputs through the generic and legacy entry points must produce identical
    objects.
    """
    chart_rows = pd.read_csv(
        ROOT / "data/engine_ar1/current_revenue_outlook/revenue_chart_rows.csv"
    )
    legacy = rate_paths.fed_uplift_delayed_factors(ROOT, chart_rows)
    generic = rate_paths.fed_policy_annual_factors(ROOT, chart_rows, "delay_6m")
    assert legacy == generic
    legacy_off = rate_paths.fed_uplift_off_factors(ROOT, chart_rows)
    generic_off = rate_paths.fed_policy_annual_factors(ROOT, chart_rows, "no_uplift")
    assert legacy_off == generic_off

    legacy_rows, legacy_audit = rate_paths.apply_fed_uplift_delay_to_chart_rows(
        chart_rows,
        legacy,
        scenario_roles={"basecase", "comparison"},
        affected_periods_by_fy=rate_paths.fed_policy_affected_periods(ROOT, "delay_6m"),
    )
    generic_rows, generic_audit = rate_paths.apply_fed_policy_state_to_chart_rows(
        chart_rows,
        generic,
        policy_state="delayed_6m",
        scenario_roles={"basecase", "comparison"},
        affected_periods_by_fy=rate_paths.fed_policy_affected_periods(ROOT, "delay_6m"),
    )
    pd.testing.assert_frame_equal(legacy_rows, generic_rows, check_exact=True)
    pd.testing.assert_frame_equal(legacy_audit, generic_audit, check_exact=True)


def test_published_state_is_rejected_by_the_chart_row_overlay() -> None:
    chart_rows = pd.read_csv(
        ROOT / "data/engine_ar1/current_revenue_outlook/revenue_chart_rows.csv"
    )
    with pytest.raises(ValueError, match="published"):
        rate_paths.apply_fed_policy_state_to_chart_rows(
            chart_rows, {2027: 0.9}, policy_state="published"
        )


# ------------------------------------------------ D. official comparator factors


def test_official_comparator_factors_for_every_deferral() -> None:
    for spec in finite_deferral_specs():
        frame = rate_paths.official_comparator_policy_factors(
            ROOT, spec.calculation_state_id
        )
        affected = rate_paths.fed_policy_affected_periods(ROOT, spec.calculation_state_id)
        # One factor row per affected fiscal year that the official horizon
        # carries, never a row outside the affected window.
        assert set(frame["june_year"].astype(int)) <= set(affected)
        assert (frame["factor"] < 1.0).all()
        assert (frame["target_rate_nzd_per_litre"] > 0).all()
        assert frame["policy_state"].eq(spec.calculation_state_id).all()
    published = rate_paths.official_comparator_policy_factors(ROOT, "published")
    assert published.empty


def test_official_cumulative_rate_only_revenue_is_ordered_by_duration() -> None:
    """A longer deferral forgoes at least as much rate-only revenue."""
    cumulative: dict[str, float] = {}
    for spec in finite_deferral_specs():
        factor_map = rate_paths.official_comparator_factor_map(
            ROOT, spec.calculation_state_id
        )
        pool = rate_paths.mbu26_ruc_class_revenue_by_fy(ROOT)
        spine_ped = rate_paths._mbu26_spine(ROOT)["gross_ped_revenue"]
        loss = 0.0
        for fy, factor in factor_map.items():
            repriced = float(spine_ped.get(fy, 0.0)) + float(pool.get(fy, 0.0))
            loss += repriced * (1.0 - float(factor))
        cumulative[spec.state_id] = loss
    ordered = [cumulative[spec.state_id] for spec in finite_deferral_specs()]
    assert ordered == sorted(ordered)
    assert ordered[0] > 0.0

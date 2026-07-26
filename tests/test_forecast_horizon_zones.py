"""The Revenue Outlook is read at June-year level, so the validated-horizon
boundary must be visible there. FY2029 straddles H12 and FY2030 is entirely
H13+, which was previously unmarked on every fiscal row."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from model_dashboard.forecast_imports import (
    FORECAST_HORIZON_ZONE_ACTUAL,
    FORECAST_HORIZON_ZONE_EXTRAPOLATION,
    FORECAST_HORIZON_ZONE_STRADDLE,
    FORECAST_HORIZON_ZONE_VALIDATED,
    LONG_RANGE_EXTRAPOLATION_WARNING,
    june_year_horizon_profile,
    june_year_quarters,
)
from model_dashboard.revenue_outlook import (
    annotate_forecast_horizon_zones,
    load_revenue_outlook_pack,
)

ROOT = Path(__file__).resolve().parents[1]
TRAINING_CUTOFF = "2025Q4"


def test_june_year_quarters_are_nz_fiscal_years():
    assert june_year_quarters(2030) == ("2029Q3", "2029Q4", "2030Q1", "2030Q2")


@pytest.mark.parametrize(
    ("june_year", "zone", "beyond"),
    [
        (2025, FORECAST_HORIZON_ZONE_ACTUAL, 0),
        (2026, FORECAST_HORIZON_ZONE_VALIDATED, 0),
        (2028, FORECAST_HORIZON_ZONE_VALIDATED, 0),
        (2029, FORECAST_HORIZON_ZONE_STRADDLE, 2),
        (2030, FORECAST_HORIZON_ZONE_EXTRAPOLATION, 4),
        (2050, FORECAST_HORIZON_ZONE_EXTRAPOLATION, 4),
    ],
)
def test_june_year_zone_classification(june_year, zone, beyond):
    profile = june_year_horizon_profile(june_year, TRAINING_CUTOFF)
    assert profile["horizon_zone"] == zone
    assert profile["quarters_beyond_validated_horizon"] == beyond


def test_fy2030_is_entirely_beyond_the_validated_horizon():
    """The headline MBU26 gap year is not backtest-supported at any quarter."""

    profile = june_year_horizon_profile(2030, TRAINING_CUTOFF)
    assert profile["first_horizon"] == 15
    assert profile["last_horizon"] == 18
    assert profile["share_beyond_validated_horizon"] == 1.0


def test_committed_pack_marks_extrapolated_fiscal_years():
    pack = load_revenue_outlook_pack(repo_root=ROOT)
    assert pack is not None
    rows = pack.revenue_chart_rows
    current = rows[
        rows["time_grain"].astype(str).eq("june_year")
        & rows["scenario_name"].astype(str).eq("current_basecase")
    ]
    by_year = current.drop_duplicates("june_year").set_index("june_year")

    assert by_year.at[2028, "horizon_scope"] == "H1-H12"
    assert not str(by_year.at[2028, "horizon_validation_warning"])

    assert by_year.at[2029, "horizon_scope"] == "H1-H12/H13+"
    assert by_year.at[2030, "horizon_scope"] == "H13+"
    for june_year in (2029, 2030):
        assert (
            str(by_year.at[june_year, "horizon_validation_warning"])
            == LONG_RANGE_EXTRAPOLATION_WARNING
        )


def test_external_comparator_and_actuals_are_not_marked():
    """H1-H12 describes this model's backtests, not MBU26's or an actual."""

    pack = load_revenue_outlook_pack(repo_root=ROOT)
    rows = pack.revenue_chart_rows
    for scenario in ("mbu26_official", "actual", "historical_actual"):
        selected = rows[rows["scenario_name"].astype(str).eq(scenario)]
        if selected.empty:
            continue
        assert set(selected["horizon_zone"].astype(str)) == {""}
        assert set(selected["horizon_validation_warning"].astype(str)) == {""}


def test_training_cutoff_resolution_prefers_pack_then_governed_constant():
    from model_dashboard.mbu26_source_spine import REVENUE_MODEL_TRAINING_CUTOFF
    from model_dashboard.revenue_outlook import _model_training_cutoff

    assert (
        _model_training_cutoff({"period_rule": {"model_training_cutoff": "2024Q2"}})
        == "2024Q2"
    )
    # Declared fallback, so a pack written without the field still gets a
    # correct horizon rather than being silently left unmarked.
    assert _model_training_cutoff({}) == REVENUE_MODEL_TRAINING_CUTOFF
    assert _model_training_cutoff({"period_rule": {}}) == REVENUE_MODEL_TRAINING_CUTOFF


def test_unparseable_training_cutoff_fails_closed():
    from model_dashboard.revenue_outlook import _model_training_cutoff

    with pytest.raises(ValueError, match="not a canonical quarter"):
        _model_training_cutoff({"period_rule": {"model_training_cutoff": "sometime"}})


def test_annotation_is_a_no_op_for_quarterly_and_empty_input():
    quarterly = pd.DataFrame(
        {
            "time_grain": ["quarterly"],
            "scenario_role": ["basecase"],
            "june_year": [2030],
            "horizon_scope": ["H13+"],
        }
    )
    out = annotate_forecast_horizon_zones(
        quarterly, model_training_cutoff=TRAINING_CUTOFF
    )
    assert out.at[0, "horizon_scope"] == "H13+"
    assert str(out.at[0, "horizon_zone"]) == ""


def test_manifest_no_longer_claims_the_whole_path_is_validated():
    manifest = json.loads(
        (ROOT / "data" / "current_revenue_outlook" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    notes = manifest["data_vintage_manifest_notes"]
    cutoff_note = notes["runtime_cutoff"].lower()
    # The narrow claim (no FY2051-55 gradient extension) is retained ...
    assert "no extrapolated model extension is used" in cutoff_note
    # ... but it must no longer read as "nothing here is extrapolation".
    assert "h13+" in cutoff_note
    assert "not validated to the short-term standard" in cutoff_note
    assert "forecast_horizon_validation" in notes
    assert "2025q4" in notes["forecast_horizon_validation"].lower()

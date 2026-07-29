"""The expected inventory is governed, and a vanished series cannot hide.

The failure this guards against is self-masking. If the expected set is built
from the rows present in the frame under test, a series that disappears
entirely also disappears from the expected set, so the engine stops expecting
it and reports ``not_applicable`` - the most serious failure presenting as the
most benign status. Removing ONE row was already tested; removing the whole
family is the case that needs a governed contract to detect.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pandas as pd
import pytest

from model_dashboard import completeness_contract
from model_dashboard.completeness_contract import (
    CompletenessContractError,
    validate_frame_completeness,
)
from model_dashboard.series_inventory_contract import (
    CONTRACT_VERSION,
    GOVERNED_STAGES,
    HISTORICAL_ACTUAL_KNOWN_GAPS,
    REQUIRED_CURRENT_FYS,
    REQUIRED_OFFICIAL_FYS,
    REQUIRED_QUARTERS,
    REQUIRED_SERIES_BY_STAGE_ROLE_GRAIN,
    required_periods,
    resolved_contract_rows,
)
from model_dashboard.unit_contract import DIMENSION_BY_UNIT

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts" / "p1_unit_completeness" / "governed_series_inventory.csv"


# ------------------------------------------------------- the contract itself
def test_contract_is_static_and_never_reads_a_pack() -> None:
    """The module must not open data files; that is what made it self-masking."""
    source = inspect.getsource(
        __import__("model_dashboard.series_inventory_contract", fromlist=["x"])
    )
    for forbidden in ("read_csv", "read_parquet", "glob(", "open(", "load_"):
        assert forbidden not in source, f"the governed inventory must not read data ({forbidden})"


def test_quarterly_window_is_h1_through_h20() -> None:
    from model_dashboard.light_fleet_allocation import quarter_horizon

    assert len(REQUIRED_QUARTERS) == 20
    assert REQUIRED_QUARTERS[0] == "2026Q1" and quarter_horizon(REQUIRED_QUARTERS[0]) == 1
    assert REQUIRED_QUARTERS[-1] == "2030Q4" and quarter_horizon(REQUIRED_QUARTERS[-1]) == 20
    # H19 and H20 are the quarters the P0 fix restored; they must stay required.
    assert "2030Q3" in REQUIRED_QUARTERS and quarter_horizon("2030Q3") == 19
    assert "2030Q4" in REQUIRED_QUARTERS
    assert "2031Q1" not in REQUIRED_QUARTERS


def test_annual_windows_match_the_governed_horizons() -> None:
    assert REQUIRED_CURRENT_FYS[-1] == 2030, "FY2030 is the last decision-grade annual"
    assert 2031 not in REQUIRED_CURRENT_FYS
    assert REQUIRED_OFFICIAL_FYS[0] == 2026 and REQUIRED_OFFICIAL_FYS[-1] == 2055


def test_every_requirement_declares_a_registered_unit() -> None:
    for (stage, role, grain), items in REQUIRED_SERIES_BY_STAGE_ROLE_GRAIN.items():
        assert stage in GOVERNED_STAGES
        for item in items:
            assert item.canonical_unit in DIMENSION_BY_UNIT, (stage, role, grain, item.series_id)
            assert item.requirement in {"required", "optional", "not_applicable"}


def test_units_are_grain_specific_where_production_publishes_them_that_way() -> None:
    """The annual-only matrix could not see this; the quarterly sweep can."""
    annual = {item.series_id: item.canonical_unit
              for item in REQUIRED_SERIES_BY_STAGE_ROLE_GRAIN[("production", "basecase", "june_year")]}
    quarterly = {item.series_id: item.canonical_unit
                 for item in REQUIRED_SERIES_BY_STAGE_ROLE_GRAIN[("production", "basecase", "quarterly")]}
    assert annual["light_ruc_net_km"] == "million_km"
    assert quarterly["light_ruc_net_km"] == "km"
    assert annual["ped_vkt_per_capita"] == quarterly["ped_vkt_per_capita"] == "km_per_person"


def test_resolved_contract_artifact_matches_the_literal() -> None:
    """A committed artifact a reviewer can read, pinned to the code."""
    assert ARTIFACT.exists(), "regenerate the P1.1 evidence"
    committed = pd.read_csv(ARTIFACT)
    resolved = pd.DataFrame(resolved_contract_rows())
    assert set(committed["contract_version"]) == {CONTRACT_VERSION}
    assert len(committed) == len(resolved)
    key = ["stage", "scenario_role", "time_grain", "series_id"]
    merged = committed.sort_values(key).reset_index(drop=True)
    expected = resolved.sort_values(key).reset_index(drop=True)
    for column in ("requirement", "canonical_unit", "horizon_rule", "required_period_count"):
        assert merged[column].tolist() == expected[column].tolist(), column


def test_known_historical_gaps_are_enumerated_not_relaxed() -> None:
    """The two absent per-capita actuals are named, not covered by a tolerance."""
    assert HISTORICAL_ACTUAL_KNOWN_GAPS == (
        ("ped_vkt_per_capita", "FY2001"),
        ("ped_vkt_per_capita", "FY2002"),
    )


# --------------------------------------------- a vanished series must be seen
@pytest.mark.parametrize(
    ("series", "label"),
    [
        ("light_ruc_net_km", "current Light RUC class"),
        ("light_bev_ruc_net_km", "Light BEV RUC class"),
        ("ped_vkt_per_capita", "PED leaf"),
        ("ped_volume", "PED volume leaf"),
        ("total_nltf_net_revenue", "top aggregate"),
        ("total_ruc_net_revenue", "RUC aggregate"),
    ],
)
def test_deleting_an_entire_required_series_reports_missing_not_not_applicable(
    real_chart_rows, series, label
) -> None:
    frame = real_chart_rows[~real_chart_rows["series_id"].eq(series)]
    report = validate_frame_completeness(frame, raise_on_failure=False)
    hit = report[report["series"].eq(series)]
    assert not hit.empty, f"{label} vanished without being noticed"
    assert (hit["status"] == "missing_required_series").any(), (
        f"{label} was reported as {sorted(set(hit['status']))} instead of missing"
    )
    # Every (role, grain) that the contract REQUIRES must report the loss. The
    # only permitted not_applicable is the official comparator's quarterly
    # grain, which the contract declares the official source does not supply.
    for (role, grain), group in hit.groupby(["role", "time_grain"]):
        required_here = bool(required_periods(role, grain)) and not (
            role == "official_comparator" and grain == "quarterly"
        )
        if required_here:
            assert (group["status"] == "missing_required_series").all(), (
                f"{label} at {role}/{grain} reported {sorted(set(group['status']))}"
            )
        else:
            assert set(group["status"]) <= {"not_applicable"}
    with pytest.raises(CompletenessContractError):
        validate_frame_completeness(frame, raise_on_failure=True)


def test_deleting_an_entire_official_source_leaf_fails_closed(real_chart_rows) -> None:
    frame = real_chart_rows[
        ~(real_chart_rows["scenario_role"].eq("official_comparator")
          & real_chart_rows["series_id"].eq("net_fed_revenue"))
    ]
    report = validate_frame_completeness(frame, raise_on_failure=False)
    hit = report[report["series"].eq("net_fed_revenue") & report["role"].eq("official_comparator")]
    assert (hit["status"] == "missing_required_series").any()


def test_deleting_an_entire_required_quarterly_stream_fails_closed(real_chart_rows) -> None:
    frame = real_chart_rows[
        ~(real_chart_rows["time_grain"].eq("quarterly")
          & real_chart_rows["series_id"].eq("heavy_ruc_net_km"))
    ]
    report = validate_frame_completeness(frame, raise_on_failure=False)
    hit = report[report["series"].eq("heavy_ruc_net_km") & report["time_grain"].eq("quarterly")]
    assert (hit["status"] == "missing_required_series").any()
    # The annual grain of the same series is untouched and still available.
    annual = report[report["series"].eq("heavy_ruc_net_km") & report["time_grain"].eq("june_year")]
    assert (annual["status"] == "required_and_available").all()


def test_the_engine_no_longer_exposes_an_observed_inventory_helper() -> None:
    """The data-derived inventory is gone, not merely unused."""
    assert not hasattr(completeness_contract, "role_series_inventory"), (
        "an observed-data inventory helper must not exist; it is the self-masking defect"
    )

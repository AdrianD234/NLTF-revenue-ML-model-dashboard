from __future__ import annotations

from pathlib import Path

import pandas as pd

from model_dashboard.fuel_price_scenario import (
    FUEL_PRICE_SCENARIO_NAME as BUILDER_SCENARIO_NAME,
    FUEL_PRICE_SCENARIO_TRACE_NAME as BUILDER_SCENARIO_TRACE_NAME,
)
from model_dashboard.revenue_outlook import (
    FUEL_PRICE_SCENARIO_NAME,
    FUEL_PRICE_SCENARIO_TRACE_NAME,
    PED_COMPARISON_BEHAVIOURAL_TRACE_NAME,
    _runtime_current_trace_name,
    _runtime_trace_type,
    _trace_sort_value,
    revenue_outlook_signature,
    revenue_stack_components_frame,
)


def test_iran_war_scenario_identity_is_mirrored_exactly() -> None:
    assert FUEL_PRICE_SCENARIO_NAME == BUILDER_SCENARIO_NAME
    assert FUEL_PRICE_SCENARIO_TRACE_NAME == BUILDER_SCENARIO_TRACE_NAME


def test_fuel_price_scenario_has_a_distinct_runtime_trace_identity() -> None:
    fuel_trace = _runtime_current_trace_name(
        FUEL_PRICE_SCENARIO_NAME,
        "comparison",
        series_id="ped_vkt_per_capita",
        display_policy="keep_trace_relabel_comparison_behavioural_path",
    )
    high_trace = _runtime_current_trace_name("current_comparison_1", "comparison")

    assert fuel_trace == FUEL_PRICE_SCENARIO_TRACE_NAME
    assert high_trace == "Current finalist High population/comparison"
    assert fuel_trace != high_trace
    assert fuel_trace != PED_COMPARISON_BEHAVIOURAL_TRACE_NAME
    assert _runtime_trace_type(fuel_trace) == "current finalist Iran war comparison"


def test_fuel_price_trace_has_a_stable_position_after_high_population() -> None:
    ordered = [
        "Actual",
        "MBU26 official",
        "Current finalist Base case",
        "Current finalist High population/comparison",
        FUEL_PRICE_SCENARIO_TRACE_NAME,
        PED_COMPARISON_BEHAVIOURAL_TRACE_NAME,
    ]

    assert [_trace_sort_value(name) for name in ordered] == list(range(len(ordered)))


def test_revenue_stack_keeps_fuel_price_as_a_distinct_ordered_source() -> None:
    sources = [
        ("MBU26 official", "mbu26_official", "official_comparator"),
        ("Current finalist Base case", "current_basecase", "basecase"),
        ("Current finalist High population/comparison", "current_comparison_1", "comparison"),
        (FUEL_PRICE_SCENARIO_TRACE_NAME, FUEL_PRICE_SCENARIO_NAME, "comparison"),
    ]
    rows = pd.DataFrame(
        [
            {
                "source_path": source_path,
                "FY": 2026,
                "series_id": "gross_ped_revenue",
                "section": "FED",
                "row_role": "leaf",
                "unit": "$m nominal ex GST",
                "value": 1.0,
                "scenario_name": scenario_name,
                "scenario_role": scenario_role,
                "fed_path": "Current planned path",
            }
            for source_path, scenario_name, scenario_role in sources
        ]
    )

    stack = revenue_stack_components_frame(rows)
    source_order = (
        stack[["source_path", "source_path_order"]]
        .drop_duplicates()
        .sort_values("source_path_order", kind="stable")
    )

    assert source_order["source_path"].tolist() == [source[0] for source in sources]
    assert source_order["source_path_order"].tolist() == [0, 1, 2, 3]


def test_signature_tracks_materialized_scenario_input_wide(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack"
    scenario_input = pack_dir / "scenario_inputs" / "scenario_input_wide.parquet"
    scenario_input.parent.mkdir(parents=True)
    scenario_input.write_bytes(b"first")

    first = {
        path: (size, modified)
        for path, size, modified in revenue_outlook_signature(pack_dir, tmp_path)
    }
    signature_path = scenario_input.as_posix()
    assert signature_path in first
    assert first[signature_path][0] == len(b"first")

    scenario_input.write_bytes(b"second-version")
    second = {
        path: (size, modified)
        for path, size, modified in revenue_outlook_signature(pack_dir, tmp_path)
    }

    assert second[signature_path][0] == len(b"second-version")
    assert second[signature_path] != first[signature_path]

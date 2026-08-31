from __future__ import annotations

from pathlib import Path

import pandas as pd

from model_dashboard.conflict_fuel_paths import (
    CONFLICT_SEVERITIES,
    SCENARIO_REGISTRY,
    all_conflict_policy_variants,
    conflict_policy_variant_name,
    conflict_scenario_display_name,
    conflict_scenario_id,
    conflict_trace_name,
)
from model_dashboard.revenue_outlook import (
    PED_COMPARISON_BEHAVIOURAL_TRACE_NAME,
    _runtime_current_trace_name,
    _runtime_trace_type,
    _trace_sort_value,
    revenue_outlook_signature,
    revenue_stack_components_frame,
)


def test_conflict_registry_has_stable_low_medium_high_identity_and_six_policy_variants() -> None:
    assert tuple(SCENARIO_REGISTRY) == CONFLICT_SEVERITIES
    assert [spec.severity for spec in SCENARIO_REGISTRY.values()] == list(CONFLICT_SEVERITIES)
    assert [conflict_scenario_id(severity) for severity in CONFLICT_SEVERITIES] == [
        "middle_east_low",
        "middle_east_medium",
        "middle_east_high",
    ]
    # The LOW path is the public central case and MEDIUM is explicitly a
    # temporary Treasury shock; the scenario_ids above stay stable while the
    # reader-facing names carry the scenario hierarchy.
    assert [conflict_scenario_display_name(severity) for severity in CONFLICT_SEVERITIES] == [
        "Current conditions baseline",
        "Temporary fuel shock (Treasury Medium)",
        "Middle East conflict: High",
    ]

    # One variant per non-published governed timing state: the six finite
    # deferrals, no-uplift, and the five bespoke rate paths, per severity
    # (36 in total).
    governed_policy_variants = (
        "delay_6m",
        "delay_12m",
        "delay_18m",
        "delay_24m",
        "delay_30m",
        "delay_36m",
        "no_uplift",
        "option1_12c_10c_4c",
        "option2_9c_9c_4c",
        "option3_4c_semiannual",
        "option4_labour_4c",
        "mcert",
    )
    variants = all_conflict_policy_variants()
    assert [(variant.severity, variant.policy_variant) for variant in variants] == [
        (severity, policy_variant)
        for severity in CONFLICT_SEVERITIES
        for policy_variant in governed_policy_variants
    ]
    assert len({variant.scenario_id for variant in variants}) == 36
    for variant in variants:
        assert variant.scenario_id == conflict_policy_variant_name(
            variant.severity,
            variant.policy_variant,
        )


def test_each_conflict_scenario_has_a_distinct_runtime_trace_identity() -> None:
    high_trace = _runtime_current_trace_name("current_comparison_1", "comparison")
    assert high_trace == "Current finalist High population/comparison"
    traces = []
    for severity in CONFLICT_SEVERITIES:
        trace = _runtime_current_trace_name(
            conflict_scenario_id(severity),
            "comparison",
            series_id="ped_vkt_per_capita",
            display_policy="keep_trace_relabel_comparison_behavioural_path",
        )
        assert trace == conflict_trace_name(severity)
        assert trace != high_trace
        assert trace != PED_COMPARISON_BEHAVIOURAL_TRACE_NAME
        assert _runtime_trace_type(trace) == "current finalist Middle East conflict comparison"
        traces.append(trace)
    assert len(set(traces)) == 3


def test_conflict_traces_have_stable_severity_order_after_high_population() -> None:
    ordered = [
        "Actual",
        "MBU26 official",
        "Current finalist Base case",
        "Current finalist High population/comparison",
        *(conflict_trace_name(severity) for severity in CONFLICT_SEVERITIES),
        PED_COMPARISON_BEHAVIOURAL_TRACE_NAME,
    ]

    assert [_trace_sort_value(name) for name in ordered] == list(range(len(ordered)))


def test_revenue_stack_keeps_all_conflict_paths_as_distinct_ordered_sources() -> None:
    sources = [
        ("BEFU26 official", "befu26_official", "official_comparator"),
        ("MBU26 official", "mbu26_official", "official_comparator"),
        ("Current finalist Base case", "current_basecase", "basecase"),
        ("Current finalist High population/comparison", "current_comparison_1", "comparison"),
        *(
            (conflict_trace_name(severity), conflict_scenario_id(severity), "comparison")
            for severity in CONFLICT_SEVERITIES
        ),
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
    assert source_order["source_path_order"].tolist() == list(range(len(sources)))


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

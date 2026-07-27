"""The two scenario-input materialisation routes must stay equivalent.

`materialize_scenario_inputs()` takes N workbooks in one call;
`combine_scenario_input_dirs()` materialises each separately and merges. Both
are live and both are legitimate - the committed pack used the first, the
canonical promote -> rebuild route uses the second. They emit different
descriptive `source_policy` wording, which is approved.

What is NOT approved is the two routes silently diverging in content. This test
pins that: given the same committed workbooks, both must produce identical
scenario-input cells, long rows, wide rows and feature lineage.

See docs/PACK_PROVENANCE_FINDING.md.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from model_dashboard.scenario_inputs import (
    ScenarioWorkbookInput,
    combine_scenario_input_dirs,
    materialize_scenario_inputs,
)

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "current_revenue_outlook" / "scenario_inputs" / "raw"
# Descriptive metadata whose difference between the routes is approved.
APPROVED_METADATA_DIFFERENCES = {
    "source_policy",
    "created_at",
    "created_by",
    "repo_relative_output_dir",
    "source_manifests",
    "raw_workbook_size_limit_bytes",
    "output_files",
    "workbooks",
    "sheet_inventory",
}
CONTENT_FRAMES = (
    "scenario_input_cells",
    "scenario_input_long",
    "scenario_input_wide",
    "scenario_feature_lineage",
)


def _workbooks() -> list[ScenarioWorkbookInput]:
    found = sorted(RAW_DIR.glob("*.xlsx"))
    basecase = next((p for p in found if "basecase" in p.name.lower()), None)
    comparison = next((p for p in found if "high_population" in p.name.lower()), None)
    if basecase is None or comparison is None:
        pytest.skip("committed scenario workbooks are not present")
    return [
        ScenarioWorkbookInput(
            workbook=basecase,
            scenario_name="current_basecase",
            scenario_role="basecase",
            workbook_filename=basecase.name,
        ),
        ScenarioWorkbookInput(
            workbook=comparison,
            scenario_name="current_comparison_1",
            scenario_role="comparison",
            workbook_filename=comparison.name,
        ),
    ]


def _frame(base: Path, name: str) -> pd.DataFrame:
    path = base / f"{name}.parquet"
    if not path.exists():
        pytest.skip(f"{name} was not produced")
    frame = pd.read_parquet(path)
    # Order is not part of the contract; content is.
    return frame.sort_values(list(frame.columns), kind="stable").reset_index(drop=True)


@pytest.fixture(scope="module")
def routes(tmp_path_factory):
    workbooks = _workbooks()
    root = tmp_path_factory.mktemp("routes")

    single = root / "single"
    one_call = materialize_scenario_inputs(workbooks, single, repo_root=root)

    parts = []
    for workbook in workbooks:
        part = root / f"part_{workbook.scenario_name}"
        materialize_scenario_inputs([workbook], part, repo_root=root)
        parts.append(part)
    combined_dir = root / "combined"
    combined = combine_scenario_input_dirs(parts, combined_dir, repo_root=root)

    return {
        "single_dir": single,
        "combined_dir": combined_dir,
        "single_manifest": one_call,
        "combined_manifest": combined,
    }


@pytest.mark.parametrize("name", CONTENT_FRAMES)
def test_routes_produce_identical_content(routes, name):
    single = _frame(routes["single_dir"], name)
    combined = _frame(routes["combined_dir"], name)
    assert len(single) == len(combined), f"{name} row count differs"
    assert list(single.columns) == list(combined.columns), f"{name} columns differ"
    pd.testing.assert_frame_equal(single, combined, check_like=True, check_dtype=False)


def test_row_counts_match_between_routes(routes):
    single = routes["single_manifest"]["row_counts"]
    combined = routes["combined_manifest"]["row_counts"]
    assert single == combined


def test_only_approved_metadata_fields_differ(routes):
    single = routes["single_manifest"]
    combined = routes["combined_manifest"]
    shared = set(single) & set(combined)
    differing = {key for key in shared if single[key] != combined[key]}
    unapproved = differing - APPROVED_METADATA_DIFFERENCES
    assert not unapproved, (
        "the two materialisation routes diverged in a field that is not approved "
        f"descriptive metadata: {sorted(unapproved)}"
    )


def test_the_policy_wording_difference_is_the_expected_one(routes):
    """Pin the approved wording so a silent third variant is caught."""

    assert (
        routes["single_manifest"]["source_policy"]
        == "committed scenario input artifacts only; Streamlit must not load Excel at runtime"
    )
    assert (
        routes["combined_manifest"]["source_policy"]
        == "combined committed scenario input artifacts; Streamlit must not load Excel at runtime"
    )


def test_workbook_hashes_are_identical_between_routes(routes):
    def by_scenario(manifest):
        return {
            str(record["scenario_name"]): str(record["workbook_sha256"])
            for record in manifest["workbooks"]
        }

    assert by_scenario(routes["single_manifest"]) == by_scenario(
        routes["combined_manifest"]
    )

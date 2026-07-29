"""The completeness contract is enforced in production, not only in evidence.

Before this, the validator was called by the evidence generator and the tests
and by nothing else. That is a good audit of completeness, not fail-closed
production behaviour: a malformed required frame could reach the dashboard
merely because nobody ran the standalone generator. These gates prove the
blocking call exists at the real build and load boundaries.

The load boundary is reached through ``cached_load_revenue_outlook_pack``,
which is keyed on the pack signature, so validation is paid once per pack
rather than on every Streamlit rerun.
"""

from __future__ import annotations

import inspect
import shutil
from pathlib import Path

import pandas as pd
import pytest

from model_dashboard import revenue_outlook
from model_dashboard.completeness_contract import CompletenessContractError

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "data" / "current_revenue_outlook"


def test_the_load_boundary_calls_the_validator() -> None:
    source = inspect.getsource(revenue_outlook.load_revenue_outlook_pack)
    assert "validate_frame_completeness" in source
    assert "raise_on_failure=True" in source


def test_the_build_boundary_calls_the_validator_before_writing() -> None:
    source = inspect.getsource(revenue_outlook.build_current_revenue_outlook_runtime_pack)
    assert "validate_frame_completeness" in source
    gate = source.index("validate_frame_completeness")
    write = source.index("_write_pack_files")
    assert gate < write, "the gate must run before the pack is materialised"


def test_the_committed_pack_passes_the_production_gate() -> None:
    pack = revenue_outlook.load_revenue_outlook_pack(PACK, repo_root=ROOT)
    assert pack is not None
    assert not pack.revenue_chart_rows.empty


@pytest.mark.parametrize(
    ("series", "role", "period"),
    [
        ("total_nltf_net_revenue", "basecase", "FY2030"),
        ("light_ruc_net_km", "comparison", "FY2027"),
        ("net_fed_revenue", "official_comparator", "FY2049"),
    ],
)
def test_a_missing_required_row_cannot_reach_the_dashboard(tmp_path, series, role, period) -> None:
    """Inject the defect into a real pack and load it through production."""
    staged = tmp_path / "current_revenue_outlook"
    shutil.copytree(PACK, staged)
    rows = pd.read_parquet(staged / "revenue_chart_rows.parquet")
    damaged = rows[
        ~(
            rows["series_id"].astype(str).eq(series)
            & rows["scenario_role"].astype(str).eq(role)
            & rows["period"].astype(str).eq(period)
        )
    ]
    assert len(damaged) == len(rows) - 1, "the injection must remove exactly one row"
    damaged.to_parquet(staged / "revenue_chart_rows.parquet", index=False)
    _restamp_hashes(staged)

    with pytest.raises(CompletenessContractError) as caught:
        revenue_outlook.load_revenue_outlook_pack(staged, repo_root=ROOT)
    record = caught.value.record
    assert record.series == series and record.period == period
    assert record.status == "missing_derived_output"


def test_a_missing_required_quarter_cannot_reach_the_dashboard(tmp_path) -> None:
    staged = tmp_path / "current_revenue_outlook"
    shutil.copytree(PACK, staged)
    rows = pd.read_parquet(staged / "revenue_chart_rows.parquet")
    damaged = rows[
        ~(
            rows["time_grain"].astype(str).eq("quarterly")
            & rows["series_id"].astype(str).eq("light_ruc_net_km")
            & rows["period"].astype(str).eq("2030Q4")
        )
    ]
    damaged.to_parquet(staged / "revenue_chart_rows.parquet", index=False)
    _restamp_hashes(staged)

    with pytest.raises(CompletenessContractError) as caught:
        revenue_outlook.load_revenue_outlook_pack(staged, repo_root=ROOT)
    assert caught.value.record.period == "2030Q4"
    assert caught.value.record.horizon_state == "within_h20"


def test_intentional_h21_withholding_still_loads(tmp_path) -> None:
    """The gate must not turn governed withholding into a production failure."""
    pack = revenue_outlook.load_revenue_outlook_pack(PACK, repo_root=ROOT)
    rows = pack.revenue_chart_rows
    current = rows[rows["scenario_role"].astype(str).isin(["basecase", "comparison"])]
    quarterly = current[current["time_grain"].astype(str).eq("quarterly")]
    assert not quarterly.empty
    assert quarterly["period"].astype(str).max() == "2030Q4", (
        "H21+ must remain absent from the decision-facing frame, and the pack must still load"
    )


def _restamp_hashes(pack_dir: Path) -> None:
    """Re-stamp the manifest hash for the file the test just rewrote.

    The manifest hash check runs before the completeness gate and would
    otherwise fire first, so the test would prove only that hashing works.
    Re-stamping makes the damaged pack byte-consistent, which is exactly the
    adversarial case: a pack that passes every integrity check and is still
    missing a required row. The completeness gate must be what stops it.
    """
    import hashlib
    import json

    manifest_path = pack_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    output_hashes = manifest.get("output_hashes")
    assert isinstance(output_hashes, dict), "expected a hash-backed pack"
    for name, metadata in output_hashes.items():
        path = pack_dir / str(name)
        if isinstance(metadata, dict) and path.exists():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            metadata["sha256"] = digest
            if "bytes" in metadata:
                metadata["bytes"] = path.stat().st_size
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

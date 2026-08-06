"""Fast fail-closed gate for the Databricks App bundle contract.

Guards the deployment boundary without running any model code:

- every file the policy selects into the bundle stays under the 9 MiB warning
  line (Databricks Apps hard-fails at 10 MiB);
- every oversized tracked source file is explicitly classified;
- the compact Parquet replacements exist, stay small, and match their CSV
  sources;
- audit-only exclusions (the candidate-rescue ZIP, tests/docs/deliverables,
  Git metadata) can never re-enter the bundle silently;
- the two narrow runtime guards this bundle depends on keep their shape: the
  pack loader's CSV-twin tolerance and the replay digest's audit-archive
  exclusion.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "deployment" / "databricks_app_bundle_policy.json"
CANDIDATE_RESCUE_ZIP = (
    "data/dashboard_evidence_pack_reproducibility/ped_inner_hpo/source_artifacts/"
    "candidate_rescue/candidate_rescue_outputs_run_20260521_163105_20260521_163707.zip"
)


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_databricks_app_bundle",
        ROOT / "scripts" / "build_databricks_app_bundle.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def builder():
    return _load_builder()


@pytest.fixture(scope="module")
def policy(builder):
    return builder.load_policy(POLICY_PATH)


@pytest.fixture(scope="module")
def tracked(builder):
    return builder.git_tracked_files(ROOT)


@pytest.fixture(scope="module")
def selection(builder, policy, tracked):
    selected = builder.select_files(policy, tracked)
    builder.enforce_replacements(policy, selected)
    builder.enforce_required(policy, selected)
    builder.enforce_forbidden(selected)
    return selected


def test_selection_is_classified_and_size_safe(builder, policy, tracked, selection):
    """Every oversized tracked file is classified; nothing selected breaches
    the warning threshold without an explicit exemption."""
    report = builder.enforce_oversized_classified(policy, ROOT, tracked, selection)
    assert report, "expected the known oversized files to be reported"
    warning = int(policy["warning_file_bytes"])
    exempt = set(policy.get("warning_exemptions", []))
    oversized = [
        path
        for path in selection
        if (ROOT / path).is_file()
        and (ROOT / path).stat().st_size > warning
        and path not in exempt
    ]
    assert oversized == [], f"selected bundle files exceed 9 MiB: {oversized}"


def test_unclassified_oversized_file_fails_the_build(builder, policy, tracked, selection):
    stripped = dict(policy)
    stripped["omitted_files"] = []
    with pytest.raises(builder.BundleBuildError, match="nclassified oversized|not selected"):
        pruned = {
            path: record
            for path, record in selection.items()
            if path != CANDIDATE_RESCUE_ZIP
        }
        builder.enforce_oversized_classified(stripped, ROOT, tracked, pruned)


def test_forbidden_and_audit_content_never_selected(selection):
    for path in selection:
        head = path.split("/", 1)[0]
        assert head not in {".git", "tests", "docs", "deliverables"}, path
    assert CANDIDATE_RESCUE_ZIP not in selection
    assert (
        "data/revenue_model_source_pack/2026_05_19/canonical_revenue_long.csv"
        not in selection
    )


def test_replaced_csvs_are_dropped_and_parquets_kept(policy, selection):
    warning = int(policy["warning_file_bytes"])
    for entry in policy["parquet_replacements"]:
        assert entry["csv"] not in selection, entry["csv"]
        assert entry["parquet"] in selection, entry["parquet"]
        parquet_path = ROOT / entry["parquet"]
        assert parquet_path.is_file(), entry["parquet"]
        assert parquet_path.stat().st_size <= warning


@pytest.mark.parametrize(
    "entry_index",
    range(6),
)
def test_parquet_replacement_matches_csv_source(policy, entry_index):
    """Sampled value equivalence between each replaced CSV and its Parquet."""
    entry = policy["parquet_replacements"][entry_index]
    csv_path = ROOT / entry["csv"]
    parquet_path = ROOT / entry["parquet"]
    if not csv_path.is_file():
        pytest.skip(f"{entry['csv']} not present in this checkout")
    parquet_frame = pd.read_parquet(parquet_path)
    csv_frame = pd.read_csv(csv_path)
    assert list(parquet_frame.columns) == list(csv_frame.columns)
    assert len(parquet_frame) == len(csv_frame)
    probe_rows = sorted({0, len(parquet_frame) // 2, len(parquet_frame) - 1})

    def normalise(value):
        # A CSV round-trip cannot distinguish an empty string from a missing
        # value, and the pack writer stringifies missing values as "nan" in
        # Parquet object columns; treat all of those as absent so only real
        # content differences fail.
        if pd.isna(value):
            return None
        if isinstance(value, str) and value.strip().lower() in {"", "nan", "none", "null", "<na>"}:
            return None
        return value

    for row in probe_rows:
        for column in parquet_frame.columns:
            left = normalise(parquet_frame.iloc[row][column])
            right = normalise(csv_frame.iloc[row][column])
            if left is None or right is None:
                assert left is None and right is None, (row, column, left, right)
            elif isinstance(left, float) or isinstance(right, float):
                assert float(left) == pytest.approx(float(right), rel=1e-12), (
                    row,
                    column,
                )
            else:
                assert str(left) == str(right), (row, column)


def test_runtime_required_files_are_selected(selection):
    from model_dashboard.revenue_outlook import RUNTIME_REVENUE_OUTLOOK_FILES

    for engine_dir in ("data/current_revenue_outlook", "data/engine_ar1/current_revenue_outlook"):
        assert f"{engine_dir}/manifest.json" in selection
        for name in RUNTIME_REVENUE_OUTLOOK_FILES:
            assert f"{engine_dir}/{name}" in selection, f"{engine_dir}/{name}"
    for required in (
        "app.py",
        "requirements.txt",
        ".streamlit/config.toml",
        "references/BEFU26 revenue forecast.xlsx",
        "forecast_runner_manifest.json",
        "data/revenue_outlook_replay_cache/ar1/manifest.json",
        "data/revenue_outlook_replay_cache/ensemble/manifest.json",
        "data/revenue_outlook_policy_runtime/ar1/manifest.json",
        "data/revenue_outlook_policy_runtime/ensemble/manifest.json",
        "data/revenue_outlook_quarterly_display/manifest.json",
        "data/revenue_outlook_uncertainty/manifest.json",
        "data/revenue_model_source_pack/2026_05_19/manifest.json",
        "artifacts/long_horizon_validation/long_horizon_june_year_errors.csv",
        "pipeline/vnext_forward.py",
        "sitecustomize.py",
    ):
        assert required in selection, required


def test_replay_digest_excludes_only_the_audit_archive():
    from model_dashboard.revenue_outlook_replay_cache import _digest_excluded

    assert _digest_excluded(CANDIDATE_RESCUE_ZIP)
    assert not _digest_excluded(
        "data/dashboard_evidence_pack_reproducibility/ped_vnext/manifest.json"
    )
    assert not _digest_excluded(
        "data/dashboard_evidence_pack_reproducibility/ped_inner_hpo/"
        "source_artifacts/scripts/stage1_candidate_rescue_constrained_stacking_audit.py"
    )
    for engine in ("ar1", "ensemble"):
        manifest = json.loads(
            (ROOT / "data" / "revenue_outlook_replay_cache" / engine / "manifest.json")
            .read_text(encoding="utf-8")
        )
        recorded = manifest.get("provenance", {}).get("source_hashes", {})
        assert recorded, engine
        assert CANDIDATE_RESCUE_ZIP not in recorded, (
            f"{engine} replay cache still pins the audit archive; rebuild with "
            "scripts/build_revenue_outlook_replay_cache.py --all"
        )


def test_pack_loader_tolerates_missing_csv_only_with_valid_parquet(tmp_path):
    from model_dashboard.revenue_outlook import _validate_output_hashes

    parquet_bytes = b"not-really-parquet-but-hashable"
    (tmp_path / "table.parquet").write_bytes(parquet_bytes)
    good_hash = hashlib.sha256(parquet_bytes).hexdigest()

    def run(output_hashes):
        errors = _validate_output_hashes(tmp_path, {"output_hashes": output_hashes})
        return [error for error in errors if error.startswith("table.")]

    # Missing CSV with a present, hash-valid Parquet twin: tolerated.
    assert run(
        {
            "table.parquet": {"sha256": good_hash},
            "table.csv": {"sha256": "0" * 64},
        }
    ) == []
    # Missing CSV whose Parquet twin hash does NOT match: still an error.
    assert run(
        {
            "table.parquet": {"sha256": "0" * 64},
            "table.csv": {"sha256": "0" * 64},
        }
    ) == ["table.csv is missing.", "table.parquet hash mismatch."]
    # Missing Parquet is always an error, twin or no twin.
    assert "other.parquet is missing." in [
        error
        for error in _validate_output_hashes(
            tmp_path, {"output_hashes": {"other.parquet": {"sha256": good_hash}}}
        )
        if error.startswith("other.")
    ]

"""Invariance gates for the BEFU26 official-vintage branch.

These pin the things the BEFU26 work must NOT have changed: the frozen MBU26
pack, the Q1-2026 actuals history, promoted fitted states, and the governed
separation between the two vintage roles. They fail loudly if a later change
quietly rewrites a prior vintage or lets an official comparator inherit a
Current policy overlay.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from model_dashboard import official_vintage as ov

ROOT = Path(__file__).resolve().parents[1]
MBU26_PACK = ROOT / "data" / "revenue_model_source_pack" / "mbu26_annual_spine"
BASELINE_HASHES = ROOT / "artifacts" / "official_vintage_befu26" / "mbu26_pack_baseline_hashes.txt"
RUNTIME_PACKS = (
    ("ensemble", ROOT / "data" / "current_revenue_outlook"),
    ("ar1", ROOT / "data" / "engine_ar1" / "current_revenue_outlook"),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _baseline_entries() -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in BASELINE_HASHES.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 3:
            entries[parts[2]] = parts[0].lower()
    return entries


def test_mbu26_pack_is_byte_identical_to_the_branch_baseline() -> None:
    """The prior official vintage is frozen: no value may drift."""
    baseline = _baseline_entries()
    assert len(baseline) == 18, "baseline inventory should cover all 18 MBU26 pack files"
    actual = {path.name: _sha256(path) for path in MBU26_PACK.iterdir() if path.is_file()}
    assert actual == baseline


def test_mbu26_remains_selectable_as_a_prior_vintage() -> None:
    entry = ov.official_vintage_entry("MBU26", ROOT)
    assert entry["available"] is True
    assert entry["status"] == "superseded_official_vintage_available_for_comparison"
    assert entry["is_default_comparator"] is False
    assert entry["is_default_bridge_vintage"] is False
    assert "MBU26" in dict(ov.official_vintage_choices(ROOT))


@pytest.mark.parametrize("engine,pack_dir", RUNTIME_PACKS)
def test_runtime_packs_separate_the_two_vintage_roles(engine: str, pack_dir: Path) -> None:
    manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    block = manifest["official_vintages"]
    assert block["official_comparator_vintage_id"] == "PREBU26"
    assert block["bridge_assumption_vintage_id"] == "BEFU26"
    # The fields are separately auditable, so an analyst can reproduce Current
    # on one vintage's bridge against another vintage's published path.
    assert set(block["available"]) == {"PREBU26", "BEFU26", "MBU26"}
    for vintage_id, entry in block["available"].items():
        assert entry["workbook_sha256"], f"{vintage_id} must record its workbook hash"
        assert entry["manifest_sha256"], f"{vintage_id} must record its pack manifest hash"
    assert manifest["period_rule"]["official_comparator_cutoff_by_vintage"] == {
        "PREBU26": 2055,
        "BEFU26": 2055,
        "MBU26": 2055,
    }
    # Current keeps its own horizon, independent of any official source.
    assert int(manifest["period_rule"]["runtime_cutoff_fy"]) == 2030


@pytest.mark.parametrize("engine,pack_dir", RUNTIME_PACKS)
def test_no_official_vintage_carries_a_current_policy_overlay_by_default(
    engine: str, pack_dir: Path
) -> None:
    """Published official rows ship on the published path, never a counterfactual."""
    chart = pd.read_csv(pack_dir / "revenue_chart_rows.csv", low_memory=False)
    official = chart[chart["scenario_role"].astype(str).eq("official_comparator")]
    assert not official.empty
    # Each official vintage's rows carry its own release round as fed_path,
    # never a Current policy path.
    assert set(official["fed_path"].dropna().astype(str)) == {"PREBU26", "BEFU26", "MBU26"}
    for column in ("trace_name", "scenario_name"):
        values = set(official[column].dropna().astype(str))
        assert not any("deferred" in value.lower() or "uplift" in value.lower() for value in values), (
            f"official {column} must never present a counterfactual as published: {values}"
        )


@pytest.mark.parametrize("engine,pack_dir", RUNTIME_PACKS)
def test_actual_line_is_governed_and_not_replaced_by_a_vintage_history(
    engine: str, pack_dir: Path
) -> None:
    chart = pd.read_csv(pack_dir / "revenue_chart_rows.csv", low_memory=False)
    actual = chart[chart["trace_name"].astype(str).eq("Actual")]
    assert not actual.empty
    # One Actual trace only - flipping the comparator must not fork history
    # into a per-vintage actual line.
    assert set(actual["scenario_name"].astype(str)) <= {"actual", "historical_actual"}
    assert set(actual["scenario_role"].dropna().astype(str)) == {"actual"}
    # The plotted annual actual line ends at FY2025. FY2026 actual-to-date
    # rows exist as nowcast inputs but are never plotted as actuals.
    plotted = actual[
        actual["time_grain"].astype(str).eq("june_year")
        & actual["row_type"].astype(str).eq("historical_actual")
    ]
    assert not plotted.empty
    assert int(pd.to_numeric(plotted["june_year"], errors="coerce").max()) == 2025
    # No official-vintage scenario may masquerade as the actual line.
    assert not actual["scenario_name"].astype(str).str.contains("official").any()


def test_befu26_published_values_match_the_workbook_pack_exactly() -> None:
    """Every displayed BEFU26 official value traces to the materialized pack."""
    pack = ov.load_official_vintage("BEFU26", repo_root=ROOT)
    assert pack is not None
    official = pack.official_annual.copy()
    official["value"] = pd.to_numeric(official["value"], errors="coerce")
    source = {
        (str(row.series_id), int(row.FY)): float(row.value)
        for row in official.itertuples()
        if pd.notna(row.value)
    }
    chart = pd.read_csv(
        ROOT / "data" / "current_revenue_outlook" / "revenue_chart_rows.csv", low_memory=False
    )
    displayed = chart[
        chart["scenario_name"].astype(str).eq("befu26_official")
        & chart["time_grain"].astype(str).eq("june_year")
    ].copy()
    assert not displayed.empty
    mismatches = []
    for row in displayed.itertuples():
        key = (str(row.series_id), int(float(row.june_year)))
        value = pd.to_numeric(pd.Series([row.value]), errors="coerce").iloc[0]
        if key in source and pd.notna(value) and float(value) != source[key]:
            mismatches.append((key, float(value), source[key]))
    assert mismatches == [], f"displayed BEFU26 values diverge from the pack: {mismatches[:5]}"


def test_every_revenue_bridge_uses_the_registered_bridge_vintage() -> None:
    """No code path may bridge activity to revenue on a different vintage.

    Regression gate for a real defect on this branch: the Treasury macro
    replay still called ``load_mbu26_annual_spine`` to turn replayed activity
    into revenue while the committed packs were rebuilt on the BEFU26 bridge.
    Mixing the two vintages broke the Current RUC identity (Total RUC no
    longer equalled class leaves less administration) by ~2.5e-3 - small
    enough to slip past a chart, large enough to fail the governed 1e-6
    reconciliation gate.
    """
    offenders: list[str] = []
    for directory in ("model_dashboard", "scripts"):
        for path in (ROOT / directory).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            rel = path.relative_to(ROOT).as_posix()
            if rel in {
                "model_dashboard/mbu26_source_spine.py",
                "model_dashboard/revenue_outlook.py",
                "scripts/materialize_mbu26_annual_spine.py",
                "scripts/build_corrected_mbu26_reconciliation.py",
            }:
                continue
            source = path.read_text(encoding="utf-8")
            if "current_forecast_annual_from_mbu26(" in source and "load_mbu26_annual_spine" in source:
                offenders.append(rel)
    assert offenders == [], (
        "these modules bridge activity to revenue using the MBU26 spine instead of the "
        f"registered bridge-assumption vintage: {offenders}"
    )


def test_current_ruc_identity_closes_in_the_committed_packs() -> None:
    """Total RUC must equal class leaves less administration, exactly."""
    for _engine, pack_dir in RUNTIME_PACKS:
        line = pd.read_csv(pack_dir / "revenue_line_reconciliation.csv", low_memory=False)
        current = line[line["source_path"].astype(str).eq("Current finalist Base case")]
        wide = current.pivot_table(index="FY", columns="series_id", values="value", aggfunc="first")
        classes = [
            "light_ruc_net_revenue",
            "light_bev_ruc_net_revenue",
            "phev_ruc_net_revenue",
            "heavy_ruc_net_revenue",
            "heavy_bev_ruc_net_revenue",
        ]
        for fy in (2026, 2027, 2028, 2029, 2030):
            residual = wide.loc[fy, "total_ruc_net_revenue"] - (
                sum(wide.loc[fy, series] for series in classes) - wide.loc[fy, "ruc_admin_revenue"]
            )
            assert abs(float(residual)) < 1e-6, f"{pack_dir.name} FY{fy} residual {residual}"


def test_lambda_migration_path_has_not_returned() -> None:
    """The retired lambda allocation must not reappear in the runtime bridge."""
    chart = pd.read_csv(
        ROOT / "data" / "current_revenue_outlook" / "revenue_chart_rows.csv", low_memory=False
    )
    bases = chart.get("source_basis", pd.Series(dtype=str)).fillna("").astype(str)
    assert not bases.str.contains("lambda migration total", case=False).any()
    assert not bases.str.contains("lambda-reduced", case=False).any()

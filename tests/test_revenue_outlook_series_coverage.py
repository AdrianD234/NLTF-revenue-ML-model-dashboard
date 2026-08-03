"""Series coverage and quarterly display contract.

Two claims are under test. First, that the BEFU26 Light petrol VKT official
line is restored FROM ITS SOURCE - the values must reconcile cell for cell to
the published vintage pack, not merely exist. Second, that every quarterly row
the dashboard may show is governed: declared in the contract, reconciled to its
annual anchor, labelled derived where it is derived, and stopped at FY2050.

Several tests here assert their own join is non-vacuous before asserting the
property. A coverage test that silently matched nothing would report the exact
failure it exists to catch as a pass.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from model_dashboard import revenue_outlook_series_coverage as coverage
from model_dashboard.official_vintage import load_official_vintage, official_vintage_choices
from model_dashboard.rate_paths import (
    FED_POLICY_STATE_DELAYED_6M,
    FED_POLICY_STATE_NO_UPLIFT,
)
from model_dashboard.revenue_outlook import CURRENT_REVENUE_OUTLOOK_DIR

ROOT = Path(__file__).resolve().parents[1]
AR1_CHART_ROWS = ROOT / "data" / "engine_ar1" / "current_revenue_outlook" / "revenue_chart_rows.parquet"

# The label the Revenue Outlook selector shows for the series this branch restores.
LIGHT_PETROL_LABEL = "Light petrol VKT"
LIGHT_PETROL_ID = "light_petrol_vkt"


@pytest.fixture(scope="module")
def chart_rows() -> pd.DataFrame:
    return pd.read_parquet(ROOT / CURRENT_REVENUE_OUTLOOK_DIR / "revenue_chart_rows.parquet")


@pytest.fixture(scope="module")
def pack() -> coverage.QuarterlyDisplayPack:
    return coverage.load_quarterly_display_pack(ROOT)


@pytest.fixture(scope="module")
def official_source() -> dict[str, pd.DataFrame]:
    return {
        vintage_id: load_official_vintage(vintage_id, repo_root=ROOT).official_annual
        for vintage_id, _display in official_vintage_choices(ROOT)
    }


# --------------------------------------------------------------- identity


def test_canonical_series_id_resolves_labels_ids_and_aliases() -> None:
    assert coverage.canonical_series_id(LIGHT_PETROL_LABEL) == LIGHT_PETROL_ID
    assert coverage.canonical_series_id(LIGHT_PETROL_ID) == LIGHT_PETROL_ID
    # The selector's format_func renames this one on screen; both must resolve.
    assert coverage.canonical_series_id("Total RUC all classes") == "total_ruc_net_revenue"
    assert coverage.canonical_series_id("Net RUC revenue (all classes)") == "total_ruc_net_revenue"
    # The one governed alias in the vintage packs.
    assert coverage.canonical_series_id("light_petrol_vkt_per_capita") == "ped_vkt_per_capita"


def test_canonical_series_id_rejects_unknown_rather_than_returning_empty() -> None:
    with pytest.raises(coverage.SeriesCoverageError):
        coverage.canonical_series_id("Not a series")
    with pytest.raises(coverage.SeriesCoverageError):
        coverage.canonical_series_id("")


def test_every_selectable_series_has_exactly_one_contract(chart_rows: pd.DataFrame) -> None:
    """The selector's vocabulary and the contract must be the same set.

    Rebuilt here the way ``app._revenue_outlook_stream_options`` builds it, so a
    label the app can offer but the contract does not govern fails loudly -
    which is precisely the drift that hid the missing BEFU26 line.
    """
    labels = set(chart_rows["series_label"].dropna().astype(str))
    assert {"PED VKT per capita", "PED volume"}.issubset(labels)
    labels.add(LIGHT_PETROL_LABEL)

    contract_ids = coverage.selectable_series_ids()
    assert len(contract_ids) == len(set(contract_ids))
    assert {coverage.canonical_series_id(label) for label in labels} == set(contract_ids)

    frame = coverage.quarterly_contract_frame()
    assert len(frame) == len(contract_ids)
    assert frame["series_id"].is_unique


def test_contract_vocabularies_are_closed() -> None:
    frame = coverage.quarterly_contract_frame()
    assert set(frame["annual_semantics"]).issubset(set(coverage.ANNUAL_SEMANTICS))
    assert set(frame["quarterly_source"]).issubset(set(coverage.QUARTERLY_SOURCES))
    assert (frame["display_horizon_last_fy"] == coverage.DISPLAY_HORIZON_LAST_FY).all()


# ------------------------------------------------- the restored official line


def test_befu26_official_appears_for_light_petrol_vkt(pack: coverage.QuarterlyDisplayPack) -> None:
    rows = pack.official_annual_rows
    befu = rows[
        rows["series_id"].eq(LIGHT_PETROL_ID) & rows["trace_name"].eq("BEFU26 official")
    ]
    assert not befu.empty, "the branch's whole purpose: BEFU26 must draw for Light petrol VKT"
    assert befu["series_label"].eq(LIGHT_PETROL_LABEL).all()
    assert int(befu["june_year"].min()) == 2026
    assert int(befu["june_year"].max()) == coverage.DISPLAY_HORIZON_LAST_FY
    assert befu["scenario_role"].eq("official_comparator").all()


def test_restored_official_values_and_units_reconcile_to_source(
    pack: coverage.QuarterlyDisplayPack,
    official_source: dict[str, pd.DataFrame],
) -> None:
    """Every restored value is the published one, unit included."""
    rows = pack.official_annual_rows
    checked = 0
    for vintage_id, trace in (("BEFU26", "BEFU26 official"), ("MBU26", "MBU26 official")):
        source = official_source[vintage_id]
        source = source[source["series_id"].astype(str).eq(LIGHT_PETROL_ID)].copy()
        # Plain column names: itertuples mangles leading underscores.
        source["fy"] = pd.to_numeric(source["FY"], errors="coerce")
        source["numeric"] = pd.to_numeric(source["value"], errors="coerce")
        lookup = {
            int(row.fy): (float(row.numeric), str(row.unit))
            for row in source.dropna(subset=["fy", "numeric"]).itertuples(index=False)
        }
        block = rows[rows["series_id"].eq(LIGHT_PETROL_ID) & rows["trace_name"].eq(trace)]
        assert not block.empty
        for row in block.itertuples(index=False):
            expected_value, expected_unit = lookup[int(row.june_year)]
            assert float(row.value) == expected_value
            assert str(row.value_unit) == expected_unit == "million km"
            checked += 1
    assert checked >= 50, "join was too small to be evidence"


def test_befu26_and_mbu26_light_petrol_vkt_stay_distinct(
    pack: coverage.QuarterlyDisplayPack,
) -> None:
    rows = pack.official_annual_rows
    befu = rows[rows["trace_name"].eq("BEFU26 official") & rows["series_id"].eq(LIGHT_PETROL_ID)]
    mbu = rows[rows["trace_name"].eq("MBU26 official") & rows["series_id"].eq(LIGHT_PETROL_ID)]
    merged = befu.merge(mbu, on="june_year", suffixes=("_befu", "_mbu"))
    assert len(merged) >= 20
    differing = (merged["value_befu"] - merged["value_mbu"]).abs().gt(1e-9).sum()
    assert differing >= 20, "the two vintages must not be a relabel of one another"


def test_no_value_beyond_a_vintage_source_horizon_is_invented(
    official_source: dict[str, pd.DataFrame],
) -> None:
    rows = coverage.official_rows_for_series(
        LIGHT_PETROL_ID, repo_root=ROOT, apply_display_horizon=False
    )
    for vintage_id, trace in (("BEFU26", "BEFU26 official"), ("MBU26", "MBU26 official")):
        source = official_source[vintage_id]
        source = source[source["series_id"].astype(str).eq(LIGHT_PETROL_ID)]
        source_max = int(pd.to_numeric(source["FY"], errors="coerce").max())
        block = rows[rows["trace_name"].eq(trace)]
        assert not block.empty
        assert int(block["june_year"].max()) <= source_max


def test_restoring_the_series_moves_no_other_official_value(chart_rows: pd.DataFrame) -> None:
    """The materialisation is additive: it emits only rows nothing publishes.

    Anything else would mean an existing official value had been recomputed.
    """
    missing = coverage.missing_official_rows(chart_rows, repo_root=ROOT)
    assert not missing.empty
    assert set(missing["series_id"]) == {LIGHT_PETROL_ID}

    annual = chart_rows[chart_rows["time_grain"].eq("june_year")]
    existing = {
        (str(row.series_id), str(row.trace_name), str(row.period))
        for row in annual.itertuples(index=False)
    }
    emitted = {
        (str(row.series_id), str(row.trace_name), str(row.period))
        for row in missing.itertuples(index=False)
    }
    assert not emitted & existing


def test_restored_rows_carry_checkable_source_lineage(
    pack: coverage.QuarterlyDisplayPack,
) -> None:
    """Lineage must name a file that exists and the hash governing it.

    A lineage string pointing at a path that is not there is worse than none:
    it reads as provenance and cannot be followed.
    """
    rows = pack.official_annual_rows
    assert not rows.empty
    seen_paths: set[str] = set()
    for row in rows.itertuples(index=False):
        lineage = str(row.source)
        path_text, _, tail = lineage.partition("#")
        series_and_fy, _, digest = tail.partition("@")
        assert (ROOT / path_text).is_file(), f"lineage names a missing file: {path_text}"
        assert series_and_fy == f"{row.series_id}:FY{int(row.june_year)}"
        assert len(digest) == 16 and int(digest, 16) >= 0
        seen_paths.add(path_text)
    # Both vintages contribute, under their own registered file stems.
    assert len(seen_paths) == 2


def test_restored_rows_carry_no_placeholder_text(
    pack: coverage.QuarterlyDisplayPack,
) -> None:
    """A missing cell must read as empty, never as the string 'nan'."""
    for frame in (pack.official_annual_rows, pack.quarterly_rows):
        assert not (frame.astype(str) == "nan").any().any()


def test_no_series_outside_the_contract_is_fabricated(
    pack: coverage.QuarterlyDisplayPack,
) -> None:
    governed = set(coverage.selectable_series_ids())
    assert set(pack.quarterly_rows["series_id"]).issubset(governed)
    assert set(pack.official_annual_rows["series_id"]).issubset(governed)


def test_every_restored_official_row_has_a_source_row(
    pack: coverage.QuarterlyDisplayPack,
    official_source: dict[str, pd.DataFrame],
) -> None:
    """No emitted official row may exist without a published cell behind it."""
    source_keys: set[tuple[str, int]] = set()
    for vintage_id, frame in official_source.items():
        valued = frame[pd.to_numeric(frame["value"], errors="coerce").notna()]
        for row in valued.itertuples(index=False):
            source_keys.add((str(row.series_id), int(row.FY)))
    rows = pack.official_annual_rows
    assert not rows.empty
    for row in rows.itertuples(index=False):
        assert (str(row.series_id), int(row.june_year)) in source_keys


# --------------------------------------------------------- horizon governance


def test_no_display_row_belongs_to_fy2051_or_later(
    pack: coverage.QuarterlyDisplayPack,
) -> None:
    for frame in (pack.quarterly_rows, pack.official_annual_rows):
        assert int(pd.to_numeric(frame["june_year"]).max()) <= coverage.DISPLAY_HORIZON_LAST_FY
    quarters = pack.quarterly_rows["period"].astype(str)
    assert not quarters.empty
    fys = quarters.map(coverage.june_year_for_quarter)
    assert fys.notna().all()
    assert int(fys.max()) <= coverage.DISPLAY_HORIZON_LAST_FY
    # The calendar-year trap: 2050Q3 is an FY2051 quarter.
    assert not quarters.isin({"2050Q3", "2050Q4"}).any()


def test_display_horizon_filter_cuts_on_fiscal_not_calendar_year() -> None:
    rows = pd.DataFrame(
        {
            "period": ["2050Q1", "2050Q2", "2050Q3", "2050Q4", "2051Q1"],
            "june_year": [2050, 2050, 2051, 2051, 2051],
        }
    )
    kept = coverage.display_horizon_filter(rows)
    assert list(kept["period"]) == ["2050Q1", "2050Q2"]


def test_official_source_extends_past_the_display_horizon() -> None:
    """The FY2050 cut is doing real work, not filtering an empty tail."""
    unfiltered = coverage.official_rows_for_series(
        LIGHT_PETROL_ID, repo_root=ROOT, apply_display_horizon=False
    )
    filtered = coverage.official_rows_for_series(LIGHT_PETROL_ID, repo_root=ROOT)
    assert int(unfiltered["june_year"].max()) > coverage.DISPLAY_HORIZON_LAST_FY
    assert len(filtered) < len(unfiltered)


# ------------------------------------------------------------- reconciliation


def test_every_derived_year_reconciles_to_its_annual_anchor(
    pack: coverage.QuarterlyDisplayPack,
) -> None:
    audit = coverage.annual_reconciliation_audit(pack.quarterly_rows)
    assert len(audit) > 1500, "join was too small to be evidence"
    assert audit["reconciles"].all()
    assert float(audit["relative_residual"].max()) <= coverage.RECONCILIATION_REL_TOLERANCE


def test_reconciliation_audit_catches_a_broken_year(
    pack: coverage.QuarterlyDisplayPack,
) -> None:
    """The audit must fail when a value is wrong, or it proves nothing."""
    broken = pack.quarterly_rows.copy()
    index = broken.index[0]
    broken.loc[index, "value"] = float(broken.loc[index, "value"]) + 1.0
    audit = coverage.annual_reconciliation_audit(broken)
    assert not audit["reconciles"].all()


def test_derived_quarter_counts_complete_each_june_year(
    pack: coverage.QuarterlyDisplayPack,
) -> None:
    """Derived quarters plus published ones must make exactly four per year."""
    audit = coverage.annual_reconciliation_audit(pack.quarterly_rows)
    fixed_counts = audit["fixed_actual_quarters"].map(
        lambda text: len([part for part in str(text).split(";") if part.strip()])
    )
    assert ((audit["derived_quarters"] + fixed_counts) == 4).all()


def test_end_of_period_interpolation_hits_every_annual_anchor() -> None:
    """A level series is interpolated, never summed, and the anchor is exact."""
    anchors = [100.0, 140.0, 130.0, 0.5]
    quarters = coverage.interpolate_end_of_period_quarters(anchors)
    assert len(quarters) == 4 * len(anchors)
    for index, anchor in enumerate(anchors):
        assert quarters[4 * index + 3] == anchor
    assert (quarters >= 0.0).all()
    # First year has no earlier anchor, so it is held flat rather than back-cast.
    assert list(quarters[:4]) == [100.0] * 4


def test_no_selectable_series_is_classified_end_of_period_or_fixed() -> None:
    """The vocabulary is complete; today's selectable set simply has no members.

    Recorded as a test so a future series added under either classification has
    to come back through this file and its builder.
    """
    frame = coverage.quarterly_contract_frame()
    unused = {coverage.ANNUAL_SEMANTICS_END_OF_PERIOD, coverage.ANNUAL_SEMANTICS_FIXED}
    assert not set(frame["annual_semantics"]) & unused


# ---------------------------------------------------------------- provenance


def test_derived_rows_are_labelled_derived(pack: coverage.QuarterlyDisplayPack) -> None:
    rows = pack.quarterly_rows
    assert not rows.empty
    assert rows["coverage_row_type"].eq(coverage.COVERAGE_ROW_TYPE_DERIVED).all()
    assert rows["empirical_or_derived"].eq("derived").all()
    assert rows["data_scope"].eq(coverage.COVERAGE_ROW_TYPE_DERIVED).all()
    assert rows["value_status"].eq("derived_quarterly_display").all()
    assert rows["contract_version"].eq(coverage.CONTRACT_VERSION).all()
    assert rows["annual_source_period"].astype(str).str.startswith("FY").all()


def test_derived_rows_inherit_row_type_from_their_annual_source(
    pack: coverage.QuarterlyDisplayPack,
) -> None:
    """Downstream filters key off row_type; overwriting it would hide rows.

    ``_filter_revenue_outlook_rows`` keeps historical_actual rows regardless of
    the scenario selection. A derived Actual quarter carrying a derived-only
    row_type would fall out of that escape hatch and vanish from the chart.
    """
    rows = pack.quarterly_rows
    actual = rows[rows["trace_name"].eq("Actual")]
    assert not actual.empty
    assert actual["row_type"].eq("historical_actual").all()
    official = rows[rows["scenario_role"].eq("official_comparator")]
    assert not official.empty
    assert official["row_type"].eq("official_comparator").all()


def test_official_derived_quarters_never_claim_to_be_published_official_data(
    pack: coverage.QuarterlyDisplayPack,
) -> None:
    official = pack.quarterly_rows[
        pack.quarterly_rows["scenario_role"].eq("official_comparator")
    ]
    assert not official.empty
    assert official["source_basis"].eq(coverage.OFFICIAL_DERIVED_PROVENANCE).all()
    current = pack.quarterly_rows[
        pack.quarterly_rows["scenario_role"].ne("official_comparator")
    ]
    assert not current.empty
    assert current["source_basis"].eq(coverage.CURRENT_DERIVED_PROVENANCE).all()


def test_derivation_method_and_seasonal_basis_are_recorded(
    pack: coverage.QuarterlyDisplayPack,
) -> None:
    rows = pack.quarterly_rows
    assert rows["derivation_method"].astype(str).str.len().gt(0).all()
    assert rows["seasonal_basis"].astype(str).str.len().gt(0).all()
    identity = rows[rows["series_id"].eq("total_fed_ruc_net_revenue")]
    assert not identity.empty
    assert identity["derivation_method"].eq(coverage.METHOD_IDENTITY).all()


def test_the_composition_identity_holds_at_every_quarter(
    pack: coverage.QuarterlyDisplayPack,
) -> None:
    """Total RUC+PED must equal Net FED plus Total RUC quarter by quarter."""
    rows = pack.quarterly_rows
    keys = ["trace_name", "scenario_name", "period"]
    total = rows[rows["series_id"].eq("total_fed_ruc_net_revenue")].set_index(keys)["value"]
    fed = rows[rows["series_id"].eq("net_fed_revenue")].set_index(keys)["value"]
    ruc = rows[rows["series_id"].eq("total_ruc_net_revenue")].set_index(keys)["value"]
    joined = pd.concat({"total": total, "fed": fed, "ruc": ruc}, axis=1).dropna()
    assert len(joined) > 300, "join was too small to be evidence"
    residual = (joined["total"] - joined["fed"] - joined["ruc"]).abs()
    assert float(residual.max()) <= 1e-6


# ---------------------------------------------------- native rows are untouched


def test_native_quarterly_rows_are_not_shadowed_or_rewritten(
    chart_rows: pd.DataFrame,
    pack: coverage.QuarterlyDisplayPack,
) -> None:
    native = chart_rows[chart_rows["time_grain"].eq("quarterly")]
    assert not native.empty
    native_keys = {
        (str(row.series_id), str(row.trace_name), str(row.period))
        for row in native.itertuples(index=False)
    }
    derived_keys = {
        (str(row.series_id), str(row.trace_name), str(row.period))
        for row in pack.quarterly_rows.itertuples(index=False)
    }
    assert not native_keys & derived_keys


def test_native_series_gain_the_long_run_tail_they_were_missing(
    chart_rows: pd.DataFrame,
    pack: coverage.QuarterlyDisplayPack,
) -> None:
    """The gap the branch closes: published quarters stop, the annual path does not."""
    for series_id in ("light_ruc_net_km", "heavy_ruc_net_km", "ped_vkt_per_capita"):
        native = chart_rows[
            chart_rows["time_grain"].eq("quarterly")
            & chart_rows["series_id"].eq(series_id)
            & chart_rows["trace_name"].eq("Current finalist Base case")
        ]
        assert not native.empty
        native_last = max(native["period"].astype(str))
        derived = pack.quarterly_rows[
            pack.quarterly_rows["series_id"].eq(series_id)
            & pack.quarterly_rows["trace_name"].eq("Current finalist Base case")
        ]
        assert not derived.empty
        assert min(derived["period"].astype(str)) > native_last
        assert max(derived["period"].astype(str)) == coverage.DISPLAY_HORIZON_LAST_QUARTER


def test_a_partly_published_june_year_keeps_its_published_quarters(
    pack: coverage.QuarterlyDisplayPack,
) -> None:
    """FY2031 has two published quarters and two derived ones; both must survive."""
    rows = pack.quarterly_rows
    partial = rows[
        rows["series_id"].eq("light_ruc_net_km")
        & rows["trace_name"].eq("Current finalist Base case")
        & rows["june_year"].eq(2031)
    ]
    assert len(partial) == 2
    fixed = str(partial["fixed_actual_quarters"].iloc[0])
    assert len([part for part in fixed.split(";") if part.strip()]) == 2
    assert float(partial["fixed_actual_total"].iloc[0]) > 0.0


# ------------------------------------------------------------- policy timing


def test_governed_policy_steps_keep_their_own_quarters() -> None:
    """The step calendar comes from rate_paths and this module must not move it."""
    delayed = coverage.governed_policy_step_quarters(ROOT, policy_state=FED_POLICY_STATE_DELAYED_6M)
    assert delayed == {2027: ("2027Q1", "2027Q2")}
    no_uplift = coverage.governed_policy_step_quarters(ROOT, policy_state=FED_POLICY_STATE_NO_UPLIFT)
    assert no_uplift[2027] == ("2027Q1", "2027Q2")
    # Every governed step quarter inside the display horizon must be a quarter
    # the display can actually show, or the step would land off-chart.
    for fy, quarters in no_uplift.items():
        if fy > coverage.DISPLAY_HORIZON_LAST_FY:
            continue
        for period in quarters:
            assert coverage.june_year_for_quarter(period) == fy


def test_only_the_fed_priced_series_carry_a_rate_basis(
    pack: coverage.QuarterlyDisplayPack,
) -> None:
    """RUC has no governed quarterly rate schedule, so it must not claim one."""
    frame = coverage.quarterly_contract_frame()
    rated = set(frame.loc[frame["rate_basis"].eq(coverage.PED_RATE_BASIS), "series_id"])
    assert rated == {"gross_ped_revenue", "gross_fed_revenue", "net_fed_revenue"}
    rows = pack.quarterly_rows
    for series_id in rated:
        block = rows[rows["series_id"].eq(series_id)]
        assert not block.empty
        assert block["rate_basis"].eq(coverage.PED_RATE_BASIS).all()
    ruc = rows[rows["series_id"].eq("light_ruc_net_revenue")]
    assert not ruc.empty
    assert ruc["rate_basis"].eq("").all()


@pytest.mark.parametrize(
    ("before", "after", "rate_before", "rate_after"),
    [
        ("2026Q4", "2027Q1", 0.70024, 0.82024),
        ("2027Q4", "2028Q1", 0.82024, 0.88024),
    ],
)
def test_a_mid_year_rate_step_lands_in_its_own_quarter(
    pack: coverage.QuarterlyDisplayPack,
    before: str,
    after: str,
    rate_before: float,
    rate_after: float,
) -> None:
    """Revenue must step where the governed schedule steps, not across the year.

    Both steps sit INSIDE a fiscal year, so a volume-only indicator would
    spread the uplift back over the two quarters that preceded it. The implied
    effective rate - revenue growth divided by volume growth - is compared with
    the governed rate ratio.
    """
    rows = pack.quarterly_rows[pack.quarterly_rows["trace_name"].eq("BEFU26 official")]

    def value(series_id: str, period: str) -> float:
        block = rows[rows["series_id"].eq(series_id) & rows["period"].eq(period)]
        assert len(block) == 1, f"expected exactly one {series_id} row for {period}"
        return float(block["value"].iloc[0])

    revenue_growth = value("gross_ped_revenue", after) / value("gross_ped_revenue", before)
    volume_growth = value("ped_volume", after) / value("ped_volume", before)
    implied_rate_step = revenue_growth / volume_growth
    governed_rate_step = rate_after / rate_before
    assert implied_rate_step == pytest.approx(governed_rate_step, rel=0.01)
    # And the step is a step, not a ramp: the volume path did not move like this.
    assert volume_growth == pytest.approx(1.0, abs=0.05)


def test_policy_step_quarters_are_present_in_the_derived_ped_display(
    pack: coverage.QuarterlyDisplayPack,
) -> None:
    steps = coverage.governed_policy_step_quarters(ROOT, policy_state=FED_POLICY_STATE_DELAYED_6M)
    affected = {period for quarters in steps.values() for period in quarters}
    assert affected
    ped = pack.quarterly_rows[
        pack.quarterly_rows["series_id"].eq("gross_ped_revenue")
        & pack.quarterly_rows["trace_name"].eq("BEFU26 official")
    ]
    assert not ped.empty
    assert affected.issubset(set(ped["period"].astype(str)))


# ------------------------------------------------------------- both engines


@pytest.mark.skipif(not AR1_CHART_ROWS.is_file(), reason="ar1 engine pack is not committed")
def test_both_engines_satisfy_the_same_contract() -> None:
    """The AR1 engine pack must derive under the identical governed rules."""
    ar1 = pd.read_parquet(AR1_CHART_ROWS)
    annual = ar1[
        ar1["time_grain"].eq("june_year")
        & ar1["series_id"].isin(coverage.selectable_series_ids())
    ]
    assert not annual.empty
    derived = coverage.derive_quarterly_rows(annual, chart_rows=ar1)
    assert not derived.empty
    assert set(derived["series_id"]).issubset(set(coverage.selectable_series_ids()))
    assert int(pd.to_numeric(derived["june_year"]).max()) <= coverage.DISPLAY_HORIZON_LAST_FY
    assert derived["coverage_row_type"].eq(coverage.COVERAGE_ROW_TYPE_DERIVED).all()
    audit = coverage.annual_reconciliation_audit(derived)
    assert len(audit) > 1000
    assert audit["reconciles"].all()


# --------------------------------------------------------------- the pack


def test_pack_manifest_pins_its_sources_and_contract(
    pack: coverage.QuarterlyDisplayPack,
) -> None:
    manifest = pack.manifest
    assert manifest["schema_version"] == coverage.PACK_SCHEMA_VERSION
    assert manifest["contract_version"] == coverage.CONTRACT_VERSION
    assert manifest["display_horizon_last_fy"] == coverage.DISPLAY_HORIZON_LAST_FY
    assert manifest["source_digest"] == coverage.quarterly_display_pack_source_digest(ROOT)
    assert manifest["official_series_restored"] == [LIGHT_PETROL_ID]
    assert manifest["all_years_reconcile"] is True
    assert manifest["reconciled_series_trace_years"] > 1500


def test_a_stale_pack_fails_closed(tmp_path: Path) -> None:
    """A pack whose sources have moved must raise, not serve old numbers."""
    import json
    import shutil

    source = ROOT / coverage.QUARTERLY_DISPLAY_PACK_DIR
    target = tmp_path / "pack"
    shutil.copytree(source, target)
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_digest"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    coverage.clear_caches()
    try:
        with pytest.raises(coverage.QuarterlyDisplayPackStale):
            coverage._load_pack_cached(
                str(target), coverage.quarterly_display_pack_source_digest(ROOT)
            )
    finally:
        coverage.clear_caches()


def test_pack_build_is_byte_idempotent(tmp_path: Path) -> None:
    """Two builds on ONE machine are byte-identical.

    This is the portable half of reproducibility. Cross-platform byte equality
    is a separate and weaker claim - see
    ``test_committed_pack_matches_a_fresh_build`` for why.
    """
    first = tmp_path / "first"
    second = tmp_path / "second"
    coverage.build_quarterly_display_pack(repo_root=ROOT, output_dir=first)
    coverage.build_quarterly_display_pack(repo_root=ROOT, output_dir=second)
    names = sorted(path.name for path in first.iterdir())
    assert names, "the build produced no files"
    for name in names:
        left = hashlib.sha256((first / name).read_bytes()).hexdigest()
        right = hashlib.sha256((second / name).read_bytes()).hexdigest()
        assert left == right, f"{name} is not byte-idempotent"
    coverage.clear_caches()


def _numeric_columns(frame: pd.DataFrame) -> list[str]:
    return [
        str(column)
        for column in frame.columns
        if pd.api.types.is_numeric_dtype(frame[column])
        and not pd.api.types.is_bool_dtype(frame[column])
    ]


def _frame_differences(
    name: str,
    committed: pd.DataFrame,
    fresh: pd.DataFrame,
    *,
    rel_tol: float,
) -> list[str]:
    """Every way two pack frames disagree, structure first then numbers."""
    problems: list[str] = []
    if list(committed.columns) != list(fresh.columns):
        return [f"{name}: column set/order differs"]
    if len(committed) != len(fresh):
        return [f"{name}: {len(committed)} committed rows vs {len(fresh)} fresh"]
    for column in committed.columns:
        left, right = committed[column], fresh[column]
        if str(left.dtype) != str(right.dtype):
            problems.append(f"{name}.{column}: dtype {left.dtype} vs {right.dtype}")
            continue
        if column in _numeric_columns(committed):
            close = np.isclose(
                pd.to_numeric(left, errors="coerce").to_numpy(dtype=float),
                pd.to_numeric(right, errors="coerce").to_numpy(dtype=float),
                rtol=rel_tol,
                atol=rel_tol,
                equal_nan=True,
            )
            if not close.all():
                worst = int(np.argmin(close))
                problems.append(
                    f"{name}.{column}: {int((~close).sum())} value(s) outside {rel_tol:g}; "
                    f"first at row {worst}: {left.iloc[worst]!r} vs {right.iloc[worst]!r}"
                )
        elif not left.equals(right):
            problems.append(f"{name}.{column}: non-numeric values differ")
    return problems


def test_committed_pack_matches_a_fresh_build(tmp_path: Path) -> None:
    """The committed pack must be what the builder produces today.

    Compared structurally-exact and numerically-tolerant rather than byte for
    byte, because byte equality is NOT portable across platforms and asserting
    it made this test fail on CI for a reason that was not staleness.

    The Denton benchmarking solve goes through ``numpy.linalg.lstsq``, i.e.
    through whatever LAPACK/BLAS the platform ships. Those builds agree to
    within a unit in the last place, not bit for bit, and the reconciliation
    audit amplifies that: its ``residual`` column is a difference of nearly
    equal numbers, so a 1-ulp change in a quarter rewrites the residual's whole
    mantissa. CI demonstrated exactly this shape - the source digest matched
    (so the inputs were identical), two builds on the same Linux runner were
    byte-identical (so the build is deterministic per platform), and only the
    Windows-committed vs Linux-fresh comparison differed.

    What staleness actually looks like - a changed contract, a dropped series,
    a moved value, a renamed column - moves numbers by far more than 1e-9
    relative or changes the structure outright, and both are still caught.
    """
    fresh_dir = tmp_path / "fresh"
    coverage.build_quarterly_display_pack(repo_root=ROOT, output_dir=fresh_dir)
    committed_dir = ROOT / coverage.QUARTERLY_DISPLAY_PACK_DIR

    problems: list[str] = []
    names = sorted(path.name for path in fresh_dir.iterdir())
    assert names, "the build produced no files"
    assert names == sorted(path.name for path in committed_dir.iterdir())

    for name in names:
        fresh_path, committed_path = fresh_dir / name, committed_dir / name
        if name.endswith(".parquet"):
            problems.extend(
                _frame_differences(
                    name,
                    pd.read_parquet(committed_path),
                    pd.read_parquet(fresh_path),
                    rel_tol=1e-9,
                )
            )
        else:
            # manifest.json and the two CSVs carry no solver output, so they
            # are held to byte equality.
            if fresh_path.read_bytes() != committed_path.read_bytes():
                problems.append(f"{name}: bytes differ")

    assert not problems, "committed pack is stale; rerun the pack builder\n" + "\n".join(problems)
    coverage.clear_caches()


def test_the_pack_is_only_claimed_reproducible_to_a_stated_tolerance() -> None:
    """The manifest must state the limit, not imply bit-portability."""
    manifest = coverage.load_quarterly_display_pack(ROOT).manifest
    assert manifest["cross_platform_reproducibility"] == coverage.CROSS_PLATFORM_REPRODUCIBILITY
    assert "lstsq" in coverage.CROSS_PLATFORM_REPRODUCIBILITY
    assert manifest["all_years_reconcile"] is True
    assert manifest["reconciliation_rel_tolerance"] == coverage.RECONCILIATION_REL_TOLERANCE
    # The manifest reports the guaranteed BOUND, never a measured residual.
    # A residual is a difference of nearly equal numbers, so it has no stable
    # digits at any precision and would make the manifest uncomparable.
    assert not any("residual" in key for key in manifest)


def test_the_denton_solve_is_scale_invariant() -> None:
    """Rescaling the indicator must not move the answer at all.

    This is the property the reconditioning relies on: with ``x = ind * z``,
    dividing the indicator by a constant multiplies ``z`` by the same constant
    and leaves ``x`` alone. It also pins the bug that caused it - a raw net-km
    indicator (~3e9) used to give a materially different answer from the same
    indicator expressed in millions.
    """
    annual = np.linspace(100.0, 300.0, 25)
    shape = np.tile(np.array([1.00, 0.99, 1.01, 1.02]), 25)
    reference = coverage._denton_quarterly_split(annual, shape, average=False)
    for scale in (1e-6, 1e3, 3.4e9):
        scaled = coverage._denton_quarterly_split(annual, shape * scale, average=False)
        assert np.allclose(scaled, reference, rtol=1e-12, atol=1e-12), (
            f"indicator scale {scale:g} changed the answer"
        )


def test_the_denton_system_stays_well_conditioned_at_any_indicator_scale() -> None:
    """Pin the fix at its cause, not just at its symptom.

    The scale-invariance tests above would still pass with the badly scaled
    system, because scale invariance is a property of the mathematics and the
    bug was a property of the arithmetic. This one reconstructs the solved
    matrix and checks its conditioning directly: unnormalised, a raw net-km
    indicator (~3e9) drove it to ~6e9 and cost ~1e-6 of relative precision.
    """
    years = 25
    shape = np.tile(np.array([1.00, 0.99, 1.01, 1.02]), years)

    def condition_number(indicator: np.ndarray, *, normalise: bool) -> float:
        size = indicator.shape[0]
        weights = indicator / indicator.mean() if normalise else indicator
        difference = np.diff(np.eye(size), axis=0)
        constraint = np.zeros((years, size))
        for year in range(years):
            constraint[year, 4 * year : 4 * year + 4] = weights[4 * year : 4 * year + 4]
        kkt = np.zeros((size + years, size + years))
        kkt[:size, :size] = 2.0 * difference.T @ difference
        kkt[:size, size:] = constraint.T
        kkt[size:, :size] = constraint
        return float(np.linalg.cond(kkt))

    net_km_scale = shape * 3.4e9
    assert condition_number(net_km_scale, normalise=False) > 1e8, (
        "the unnormalised system should be the badly conditioned one"
    )
    for scale in (1.0, 1.8e3, 3.4e9):
        assert condition_number(shape * scale, normalise=True) < 1e3


def test_the_denton_solve_is_benchmark_scale_invariant() -> None:
    """Scaling every benchmark scales the answer by exactly the same factor."""
    annual = np.linspace(100.0, 300.0, 10)
    shape = np.tile(np.array([1.0, 0.98, 1.03, 0.99]), 10)
    reference = coverage._denton_quarterly_split(annual, shape, average=False)
    scaled = coverage._denton_quarterly_split(annual * 1e6, shape, average=False)
    assert np.allclose(scaled, reference * 1e6, rtol=1e-12, atol=1e-6)


# -------------------------------------------------------------- the lookup API


def test_quarterly_lookup_is_a_filter_not_a_rebuild() -> None:
    """Section 8's budget: a named lookup stays well inside 50 ms."""
    import time

    coverage.load_quarterly_display_pack(ROOT)
    for series_id in (LIGHT_PETROL_LABEL, "total_nltf_net_revenue", "ped_vkt_per_capita"):
        start = time.perf_counter()
        rows = coverage.quarterly_rows_for_selected_series(series_id, repo_root=ROOT)
        elapsed = time.perf_counter() - start
        assert not rows.empty
        assert elapsed < 0.05, f"{series_id} lookup took {elapsed * 1000:.0f} ms"


def test_lookup_derives_traces_the_pack_cannot_know_about(
    chart_rows: pd.DataFrame,
) -> None:
    """Runtime-only annual rows (policy states, conflict paths) get the same rule."""
    base = chart_rows[
        chart_rows["time_grain"].eq("june_year")
        & chart_rows["series_id"].eq("gross_ped_revenue")
        & chart_rows["trace_name"].eq("Current finalist Base case")
    ].copy()
    assert not base.empty
    base["trace_name"] = "Runtime policy state"
    base["scenario_name"] = "runtime_policy_state"

    rows = coverage.quarterly_rows_for_selected_series(
        "gross_ped_revenue",
        trace_names=["Runtime policy state"],
        annual_rows=base,
        chart_rows=chart_rows,
        repo_root=ROOT,
    )
    assert not rows.empty
    assert set(rows["trace_name"]) == {"Runtime policy state"}
    assert rows["coverage_row_type"].eq(coverage.COVERAGE_ROW_TYPE_DERIVED).all()
    audit = coverage.annual_reconciliation_audit(rows)
    assert len(audit) > 10
    assert audit["reconciles"].all()


def test_coverage_status_answers_every_owner_question(
    chart_rows: pd.DataFrame,
    pack: coverage.QuarterlyDisplayPack,
) -> None:
    table = coverage.quarterly_coverage_status(
        chart_rows,
        quarterly_rows=pack.quarterly_rows,
        official_rows=pack.official_annual_rows,
        repo_root=ROOT,
    )
    assert list(table["series_id"]) == list(coverage.selectable_series_ids())
    assert table["befu26_available"].all()
    assert table["mbu26_available"].all()
    assert table["derived_quarterly_available"].all()
    assert table["last_quarter"].eq(coverage.DISPLAY_HORIZON_LAST_QUARTER).all()
    assert table["limitation"].astype(str).str.len().gt(0).all()
    # Exactly the three published quarterly activity paths, no more.
    native = set(table.loc[table["native_quarterly_available"], "series_id"])
    assert native == {"ped_vkt_per_capita", "light_ruc_net_km", "heavy_ruc_net_km"}


def test_denton_split_can_preserve_a_mean_as_well_as_a_sum() -> None:
    """The mean-preserving branch exists for level/average series; exercise it."""
    annual = pd.array([10.0, 20.0], dtype="float64").to_numpy()
    flat = pd.array([1.0] * 8, dtype="float64").to_numpy()
    averaged = coverage._denton_quarterly_split(annual, flat, average=True)
    for index, anchor in enumerate(annual):
        quarters = averaged[4 * index : 4 * index + 4]
        assert math.isclose(math.fsum(quarters) / 4.0, anchor, rel_tol=0, abs_tol=1e-9)


def test_rate_indicator_carries_the_last_scheduled_rate_forward() -> None:
    """Past the schedule's end the planned path is flat, so carrying is exact."""
    factors = coverage._rate_indicator_factor(
        ["2026Q4", "2027Q1", "2031Q2", "2045Q1", "2050Q2"], ROOT
    )
    assert factors[0] == pytest.approx(0.70024)
    assert factors[1] == pytest.approx(0.82024)
    # Everything after the schedule's final quarter holds its final rate.
    assert factors[3] == pytest.approx(factors[2])
    assert factors[4] == pytest.approx(factors[2])


def test_denton_split_reproduces_a_flat_year_exactly() -> None:
    """A closed-form check the pack data cannot give: known input, known output."""
    values = coverage._denton_quarterly_split(
        pd.array([400.0, 800.0], dtype="float64").to_numpy(),
        pd.array([1.0] * 8, dtype="float64").to_numpy(),
        average=False,
    )
    assert math.isclose(math.fsum(values[:4]), 400.0, rel_tol=0, abs_tol=1e-9)
    assert math.isclose(math.fsum(values[4:]), 800.0, rel_tol=0, abs_tol=1e-9)
    # A flat indicator with a rising benchmark must produce a rising path, not
    # four identical quarters per year with a jump at the boundary.
    assert all(values[index] < values[index + 1] for index in range(7))

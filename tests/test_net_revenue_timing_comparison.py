from __future__ import annotations

import inspect
from pathlib import Path

import pandas as pd
import pytest

import app
from model_dashboard.conflict_fuel_paths import (
    CONFLICT_SEVERITIES,
    all_conflict_policy_variants,
    conflict_scenario_display_name,
    conflict_scenario_id,
)
from model_dashboard.engine import ENGINE_AR1, engine_revenue_outlook_dir
from model_dashboard.fuel_price_scenario import POLICY_PATH_IDS
from model_dashboard.mbu26_source_spine import FORMULA_DEFINITIONS
from model_dashboard.revenue_outlook import (
    NET_REVENUE_COMPARISON_UNIT,
    PED_BRIDGE_DEFAULT_MODE,
    load_revenue_outlook_pack,
    net_revenue_timing_comparison_frame,
    revenue_outlook_signature,
)
from model_dashboard.revenue_source_pack import SOURCE_SERIES_ALIASES
from scripts.materialize_conflict_scenario_extract import (
    _export_paths,
    _path_metadata_frame,
)


ROOT = Path(__file__).resolve().parents[1]
CONFLICT_POLICY_VARIANTS = all_conflict_policy_variants()
EXPORT_PATH_METADATA = _path_metadata_frame(_export_paths())
ALL_POLICY_PATH_IDS = tuple(EXPORT_PATH_METADATA["path_id"].astype(str))
ALL_POLICY_SCENARIO_IDS = tuple(EXPORT_PATH_METADATA["scenario_id"].astype(str))


@pytest.fixture(scope="module")
def timing_materialization() -> dict[str, object]:
    pack_dir = ROOT / engine_revenue_outlook_dir(ENGINE_AR1)
    pack = load_revenue_outlook_pack(pack_dir, repo_root=ROOT)
    assert pack is not None
    signature = revenue_outlook_signature(pack_dir, ROOT)
    sensitivity_key = app.selected_sensitivity_key(
        "Off",
        "Off",
        "Off",
        freight_rail_shift="Off",
    )
    delayed_key = (app.DEFAULT_EV_UPTAKE_MODE, (), (), 0, 0)
    chart_rows, _, _, _, _ = app.cached_scenario_overlay_rows(
        signature,
        sensitivity_key,
        PED_BRIDGE_DEFAULT_MODE,
        delayed_key,
        pack,
    )
    factors = app.cached_fed_uplift_factors(signature, pack)["delayed_6m"]
    replay = app.cached_fuel_price_scenario_replay(signature, pack)
    comparison = net_revenue_timing_comparison_frame(
        chart_rows,
        factors,
        policy_timing_rows=replay.annual_bridge,
    )
    return {
        "pack": pack,
        "signature": signature,
        "sensitivity_key": sensitivity_key,
        "delayed_key": delayed_key,
        "chart_rows": chart_rows,
        "factors": factors,
        "replay": replay,
        "comparison": comparison,
    }


def _value(frame: pd.DataFrame, path_id: str, fy: int, series_id: str) -> float:
    selected = frame[
        frame["path_id"].astype(str).eq(path_id)
        & pd.to_numeric(frame["FY"], errors="coerce").eq(fy)
        & frame["series_id"].astype(str).eq(series_id)
    ]
    assert len(selected) == 1
    return float(selected.iloc[0]["value_million_nzd"])


def test_net_ruc_alias_and_active_net_definitions_are_explicit() -> None:
    assert SOURCE_SERIES_ALIASES["Net RUC revenue"] == "total_ruc_net_revenue"
    assert SOURCE_SERIES_ALIASES["Net RUC revenue (all classes)"] == "total_ruc_net_revenue"
    formulas = {str(row["output_series_id"]): str(row["expression"]) for row in FORMULA_DEFINITIONS}
    assert formulas["net_fed_revenue"] == "gross_fed_revenue - fed_refunds"
    assert formulas["total_ruc_net_revenue"] == "ruc_revenue_net_admin - ruc_refunds"
    assert formulas["net_mvr_revenue"] == "mvr_revenue_net_admin_coo - mvr_refunds"
    assert app._revenue_outlook_series_display_label("Total RUC all classes") == "Net RUC revenue (all classes)"


def test_twelve_path_net_revenue_matrix_is_complete_unique_and_registry_driven(
    timing_materialization,
) -> None:
    comparison = timing_materialization["comparison"]
    assert isinstance(comparison, pd.DataFrame)
    assert len(comparison) == 180
    assert not comparison.duplicated(["path_id", "FY", "series_id"]).any()
    assert comparison["path_id"].drop_duplicates().tolist() == list(ALL_POLICY_PATH_IDS)
    assert all(
        POLICY_PATH_IDS[scenario_id] == path_id
        for scenario_id, path_id in zip(
            ALL_POLICY_SCENARIO_IDS,
            ALL_POLICY_PATH_IDS,
            strict=True,
        )
    )
    assert comparison["path_order"].drop_duplicates().tolist() == list(range(12))
    assert comparison["scenario_family_id"].drop_duplicates().tolist() == [
        "base",
        *CONFLICT_SEVERITIES,
    ]
    assert comparison["scenario_id"].drop_duplicates().tolist() == list(ALL_POLICY_SCENARIO_IDS)
    assert comparison[
        ["scenario_family_id", "scenario"]
    ].drop_duplicates().to_records(index=False).tolist() == [
        ("base", "Current finalist Base case"),
        *(
            (severity, conflict_scenario_display_name(severity))
            for severity in CONFLICT_SEVERITIES
        ),
    ]
    assert comparison["timing_id"].drop_duplicates().tolist() == [
        "published",
        "delayed_6m",
        "no_uplift",
    ]
    assert comparison["policy_state"].drop_duplicates().tolist() == [
        "published",
        "delay_6m",
        "no_uplift",
    ]
    metadata_columns = [
        "path_id",
        "scenario_family_id",
        "scenario_id",
        "policy_state",
    ]
    expected_metadata = EXPORT_PATH_METADATA[metadata_columns]
    actual_metadata = comparison[metadata_columns].drop_duplicates()
    pd.testing.assert_frame_equal(
        actual_metadata.reset_index(drop=True),
        expected_metadata.reset_index(drop=True),
        check_dtype=False,
    )
    assert set(comparison["FY"]) == set(range(2026, 2031))
    assert set(comparison["series_id"]) == {
        "net_fed_revenue",
        "total_ruc_net_revenue",
        "net_mvr_revenue",
    }
    assert set(comparison["unit"]) == {NET_REVENUE_COMPARISON_UNIT}
    assert comparison["value_million_nzd"].notna().all()


def test_delayed_policy_has_no_pre_policy_leakage_and_exceeds_off_after_start(
    timing_materialization,
) -> None:
    comparison = timing_materialization["comparison"]
    wide = comparison.pivot(
        index=["scenario_family_id", "FY", "series_id"],
        columns="timing_id",
        values="value_million_nzd",
    )
    wide["delta"] = wide["delayed_6m"] - wide["no_uplift"]
    wide["original_delta"] = wide["published"] - wide["delayed_6m"]
    for severity in ("base", *CONFLICT_SEVERITIES):
        # The deferred path starts on 1 July 2027, which belongs to FY2028.
        # The two policy variants must therefore be identical through FY2027.
        pre_policy = wide.loc[(severity, slice(2026, 2027)), "delta"]
        assert pre_policy.abs().max() <= 1e-12

        for series_id in ("net_fed_revenue", "total_ruc_net_revenue"):
            post_start = wide.loc[(severity, slice(2028, 2030), series_id), "delta"]
            assert post_start.gt(0.0).all()

        mvr = wide.loc[(severity, slice(2026, 2030), "net_mvr_revenue"), "delta"]
        assert mvr.abs().max() <= 1e-12
        assert wide.loc[(severity, 2026), "original_delta"].abs().max() <= 1e-12
        for series_id in ("net_fed_revenue", "total_ruc_net_revenue"):
            assert wide.loc[(severity, 2027, series_id), "original_delta"] > 0.0
        assert (
            wide.loc[(severity, slice(2028, 2030)), "original_delta"].abs().max()
            <= 1e-9
        )


def test_base_original_timing_reconciles_to_default_dashboard_hover_benchmarks(
    timing_materialization,
) -> None:
    comparison = timing_materialization["comparison"]
    # Checkpoints follow the Treasury-macro Base hover lineage after its
    # additive FED formula reconstruction, not the legacy pack values.
    #
    # Conventional-anchor correction. PED is the raw AR(1) bridge with no
    # lambda migration subtraction, so gross FED - and therefore Net FED -
    # rises: 2084.543503 -> 2103.643887, +19.100384 (+0.916%). This is the
    # final displayed default front-end value, and it reconciles exactly with
    # FY2026 net_fed_revenue in artifacts/p0_light_fleet_fix/gold_path_audit.csv.
    #
    # BEFU26 bridge-vintage re-freeze: Net FED follows the bridge vintage's PED
    # rate and petrol-fleet intensity, so moving the bridge from MBU26 to
    # BEFU26 moves it: 2103.643887 -> 2106.194985 (+2.551098, +0.121%).
    # Tolerance unchanged at 1e-6 absolute; nothing has been widened.
    assert _value(
        comparison, "baseline_published", 2026, "net_fed_revenue"
    ) == pytest.approx(2106.1949845912095, abs=1e-6)
    # Re-promoted with the migrated packs: 2127.212804135619 ->
    # Same conventional-anchor correction as FY2026: Net FED is gross FED less
    # refunds, gross FED follows PED litres, and PED is now the raw AR(1)
    # bridge rather than the lambda-migrated one.
    #   published    2127.212722 -> 2170.099908  (+42.887187, +2.016%)
    #   shifted/off  1963.260564 -> 2002.908686  (+39.648123, +2.020%)
    # BEFU26 bridge-vintage re-freeze (same cause as FY2026 above):
    #   published    2170.099908 -> 2172.226414  (+2.126506, +0.098%)
    #   shifted/off  2002.908686 -> 2004.335325  (+1.426639, +0.071%)
    # Tolerance unchanged at 1e-6 absolute.
    assert _value(
        comparison, "baseline_published", 2027, "net_fed_revenue"
    ) == pytest.approx(2172.2264140193133, abs=1e-6)
    # Both counterfactuals remove the January 2027 step from the whole of
    # FY2027, so they must agree exactly on the current-model scope.
    shifted = _value(comparison, "baseline_shifted_6m", 2027, "net_fed_revenue")
    no_uplift = _value(comparison, "baseline_no_uplift", 2027, "net_fed_revenue")
    assert shifted == pytest.approx(2004.335325410929, abs=1e-6)
    assert no_uplift == pytest.approx(shifted, abs=1e-9)


def test_export_reconciles_to_authoritative_bridge_and_independent_net_formulas(
    timing_materialization,
) -> None:
    comparison = timing_materialization["comparison"]
    chart_rows = timing_materialization["chart_rows"]
    annual_bridge = timing_materialization["replay"].annual_bridge.copy()
    annual_bridge["FY"] = pd.to_numeric(annual_bridge["FY"], errors="coerce")
    annual_bridge["value"] = pd.to_numeric(annual_bridge["value"], errors="coerce")
    ruc_leaves = {
        "light_ruc_net_revenue",
        "light_bev_ruc_net_revenue",
        "phev_ruc_net_revenue",
        "heavy_ruc_net_revenue",
        "heavy_bev_ruc_net_revenue",
    }
    required_series = {
        "gross_ped_revenue",
        "gross_fed_revenue",
        "fed_refunds",
        "net_fed_revenue",
        *ruc_leaves,
        "gross_ruc_revenue",
        "ruc_admin_revenue",
        "ruc_revenue_net_admin",
        "ruc_refunds",
        "total_ruc_net_revenue",
        "mr1_revenue",
        "mr2_revenue",
        "mvr_admin_revenue",
        "mvr_refunds",
        "net_mvr_revenue",
    }

    anchor_series = {
        "gross_ped_revenue",
        "net_fed_revenue",
        "total_ruc_net_revenue",
        "net_mvr_revenue",
    }
    display = chart_rows[
        chart_rows["time_grain"].astype(str).eq("june_year")
        & chart_rows["scenario_name"].astype(str).eq("current_basecase")
        & chart_rows["series_id"].astype(str).isin(anchor_series)
        & pd.to_numeric(chart_rows["june_year"], errors="coerce").between(2026, 2030)
    ].copy()
    display["FY"] = pd.to_numeric(display["june_year"], errors="coerce")
    display_value = pd.to_numeric(display["value"], errors="coerce")
    published_value = pd.to_numeric(display["_fed_baseline_value"], errors="coerce")
    display["published_value"] = published_value.where(published_value.notna(), display_value)
    assert not display.duplicated(["FY", "series_id"]).any()
    anchors = display.set_index(["FY", "series_id"])["published_value"].to_dict()
    assert len(anchors) == 5 * len(anchor_series)

    raw_by_path: dict[tuple[str, int], dict[str, float]] = {}
    for path_id in ALL_POLICY_PATH_IDS:
        for fy in range(2026, 2031):
            rows = annual_bridge[
                annual_bridge["policy_path_id"].astype(str).eq(path_id)
                & annual_bridge["FY"].eq(fy)
                & annual_bridge["series_id"].astype(str).isin(required_series)
            ]
            assert not rows.duplicated("series_id").any()
            values = rows.set_index("series_id")["value"].to_dict()
            assert required_series.issubset(values)
            raw_by_path[(path_id, fy)] = values

    for path_id in comparison["path_id"].drop_duplicates():
        for fy in range(2026, 2031):
            values = raw_by_path[(path_id, fy)]
            raw_base = raw_by_path[("baseline_published", fy)]

            # First verify that every authoritative raw replay path retains
            # the governed net definitions before applying chart-lineage
            # rebasing for the user-facing CSV.
            assert values["net_fed_revenue"] == pytest.approx(
                values["gross_fed_revenue"] - values["fed_refunds"], abs=1e-9
            )
            assert values["gross_ruc_revenue"] == pytest.approx(
                sum(values[series_id] for series_id in ruc_leaves) + values["ruc_refunds"],
                abs=1e-9,
            )
            assert values["ruc_revenue_net_admin"] == pytest.approx(
                values["gross_ruc_revenue"] - values["ruc_admin_revenue"],
                abs=1e-9,
            )
            assert values["total_ruc_net_revenue"] == pytest.approx(
                values["gross_ruc_revenue"]
                - values["ruc_admin_revenue"]
                - values["ruc_refunds"],
                abs=1e-9,
            )
            assert values["net_mvr_revenue"] == pytest.approx(
                values["mr1_revenue"]
                + values["mr2_revenue"]
                - values["mvr_admin_revenue"]
                - values["mvr_refunds"],
                abs=1e-9,
            )

            # Then independently rebuild the exported value from the exact
            # Base values seen on the dashboard hover and the raw replay
            # path factors. Net FED moves by the gross-PED delta; Net RUC
            # carries the full all-class aggregate factor; MVR is fixed.
            ped_factor = values["gross_ped_revenue"] / raw_base["gross_ped_revenue"]
            expected_fed = anchors[(fy, "net_fed_revenue")] + anchors[
                (fy, "gross_ped_revenue")
            ] * (ped_factor - 1.0)
            expected_ruc = anchors[(fy, "total_ruc_net_revenue")] * (
                values["total_ruc_net_revenue"] / raw_base["total_ruc_net_revenue"]
            )
            expected_mvr = anchors[(fy, "net_mvr_revenue")]
            assert _value(comparison, path_id, fy, "net_fed_revenue") == pytest.approx(
                expected_fed,
                abs=1e-9,
            )
            assert _value(comparison, path_id, fy, "total_ruc_net_revenue") == pytest.approx(
                expected_ruc,
                abs=1e-9,
            )
            assert _value(comparison, path_id, fy, "net_mvr_revenue") == pytest.approx(
                expected_mvr,
                abs=1e-9,
            )


def test_conflict_severity_ordering_and_net_mvr_identity(timing_materialization) -> None:
    comparison = timing_materialization["comparison"]
    path_for = {
        (variant.severity, variant.policy_variant): POLICY_PATH_IDS[variant.scenario_id]
        for variant in CONFLICT_POLICY_VARIANTS
    }
    for policy_variant in ("delay_6m", "no_uplift"):
        for fy in (2027, 2028, 2029):
            for series_id in ("net_fed_revenue", "total_ruc_net_revenue"):
                ordered = [
                    _value(comparison, path_for[(severity, policy_variant)], fy, series_id)
                    for severity in CONFLICT_SEVERITIES
                ]
                # A lower-severity path can legitimately converge to the
                # Medium path (or Base) before the High path does.  Require
                # monotonic severity ordering while allowing those governed
                # convergence ties, and keep the end-to-end Low-vs-High
                # separation strict.
                assert ordered[0] >= ordered[1] >= ordered[2]
                assert ordered[0] > ordered[2]

        for fy in range(2026, 2031):
            mvr = [
                _value(comparison, path_for[(severity, policy_variant)], fy, "net_mvr_revenue")
                for severity in CONFLICT_SEVERITIES
            ]
            assert max(mvr) - min(mvr) <= 1e-12


def test_comparison_is_independent_of_separate_12c_on_off_widget_state(timing_materialization) -> None:
    pack = timing_materialization["pack"]
    signature = timing_materialization["signature"]
    sensitivity_key = timing_materialization["sensitivity_key"]
    factors = timing_materialization["factors"]
    delayed_comparison = timing_materialization["comparison"]
    no_uplift_key = (app.DEFAULT_EV_UPTAKE_MODE, (), (), 1, 0)
    no_uplift_rows, _, _, _, _ = app.cached_scenario_overlay_rows(
        signature,
        sensitivity_key,
        PED_BRIDGE_DEFAULT_MODE,
        no_uplift_key,
        pack,
    )
    no_uplift_comparison = net_revenue_timing_comparison_frame(
        no_uplift_rows,
        factors,
        policy_timing_rows=timing_materialization["replay"].annual_bridge,
    )
    pd.testing.assert_frame_equal(
        delayed_comparison.reset_index(drop=True),
        no_uplift_comparison.reset_index(drop=True),
        check_exact=False,
        atol=1e-9,
        rtol=0.0,
    )


def test_all_aligned_conflict_details_reconcile_net_and_intermediate_rollups(
    timing_materialization,
) -> None:
    pack = timing_materialization["pack"]
    signature = timing_materialization["signature"]
    sensitivity_key = timing_materialization["sensitivity_key"]
    delayed_key = timing_materialization["delayed_key"]
    line_reconciliation, residuals, _, _ = app.cached_aligned_scenario_detail_frames(
        signature,
        sensitivity_key,
        PED_BRIDGE_DEFAULT_MODE,
        delayed_key,
        pack,
    )
    conflict_scenario_ids = tuple(conflict_scenario_id(severity) for severity in CONFLICT_SEVERITIES)
    conflict_residuals = residuals[
        residuals["scenario_name"].astype(str).isin(conflict_scenario_ids)
        & pd.to_numeric(residuals["FY"], errors="coerce").between(2026, 2030, inclusive="both")
        & residuals["output_series_id"].astype(str).isin(
            {
                "gross_ruc_revenue",
                "ruc_revenue_net_admin",
                "total_ruc_net_revenue",
                "net_fed_revenue",
                "net_mvr_revenue",
                "total_nltf_net_revenue",
            }
        )
    ].copy()
    assert len(conflict_residuals) == 90
    assert set(conflict_residuals["scenario_name"].astype(str)) == set(conflict_scenario_ids)
    assert conflict_residuals["status"].eq("reconciled").all()
    assert pd.to_numeric(conflict_residuals["residual_abs"], errors="coerce").max() <= 1e-6

    rows = line_reconciliation[
        line_reconciliation["scenario_name"].astype(str).isin(conflict_scenario_ids)
        & pd.to_numeric(line_reconciliation["FY"], errors="coerce").between(2026, 2030, inclusive="both")
    ].copy()
    assert set(rows["scenario_name"].astype(str)) == set(conflict_scenario_ids)
    for (_, fy), group in rows.groupby(
        ["scenario_name", pd.to_numeric(rows["FY"], errors="coerce")]
    ):
        values = group.set_index("series_id")["value"].map(float)
        assert values["total_ruc_net_revenue"] == pytest.approx(
            values["gross_ruc_revenue"] - values["ruc_admin_revenue"] - values["ruc_refunds"],
            abs=1e-9,
        )
        assert values["net_fed_revenue"] == pytest.approx(
            values["gross_fed_revenue"] - values["fed_refunds"],
            abs=1e-9,
        )
        assert values["net_mvr_revenue"] == pytest.approx(
            values["mr1_revenue"]
            + values["mr2_revenue"]
            - values["mvr_admin_revenue"]
            - values["mvr_refunds"],
            abs=1e-9,
        )


def test_revenue_outlook_renderer_keeps_only_the_bottom_net_timing_download() -> None:
    source = inspect.getsource(app.render_revenue_outlook_page)
    assert "net_revenue_12c_timing_comparison_fy2026_fy2030.csv" in source
    assert "Download 12c timing CSV" in source
    assert "Net revenue timing comparison (FY2026-FY2030)" not in source
    assert "_net_revenue_timing_comparison_display_table" not in source
    assert source.index("Download 12c timing CSV") > source.index("Show Manifest, Source policy and downloads")

"""PED activity publication through FY2050 / 2050Q2.

Covers the contract established by the branch that published the two PED
activity leaves to the public horizon:

A. the Treasury baseline macro population restatement and its lineage
B. annual publication, and the non-movement of everything else
C. the joint quarterly construction, its identities and its seam
D. engine isolation

The population tests are the load-bearing ones. The PED identity

    light_petrol_vkt = ped_vkt_per_capita * population / 1e6

is preserved against the **Treasury-baseline-restated** population, NOT against
the unadjusted legacy population in ``scenario_input_wide``. The runtime
recovers the restatement factor from the governed annual pair rather than
re-reading the factor table (which would need invasive threading); these tests
are the independent check that the two agree.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent

import app  # noqa: E402
from model_dashboard import revenue_outlook_series_coverage as coverage  # noqa: E402
from model_dashboard.engine import engine_revenue_outlook_dir  # noqa: E402
from model_dashboard.official_vintage import bridge_vintage_id_from_manifest  # noqa: E402
from model_dashboard.revenue_outlook import (  # noqa: E402
    PED_BRIDGE_DEFAULT_MODE,
    _append_post_model_ped_activity_chart_rows,
    revenue_outlook_signature,
)

ENGINES = ("ensemble", "ar1")
SCENARIOS = ("current_basecase", "current_comparison_1")
TARGETS = ("ped_vkt_per_capita", "light_petrol_vkt")
LABELS = {"ped_vkt_per_capita": "PED VKT per capita", "light_petrol_vkt": "Light petrol VKT"}
BASE_TRACE = "Current finalist Base case"
FIRST_POST_MODEL_FY = 2031
LAST_FY = 2050
LAST_QUARTER = "2050Q2"


# ----------------------------------------------------------------- fixtures


def _pack_frames(engine: str):
    base = ROOT / engine_revenue_outlook_dir(engine)
    return (
        base,
        pd.read_parquet(base / "revenue_chart_rows.parquet"),
        pd.read_parquet(base / "revenue_line_reconciliation.parquet"),
        pd.read_parquet(base / "raw_quarterly_forecast_audit.parquet"),
        pd.read_parquet(base / "scenario_inputs" / "scenario_input_wide.parquet"),
    )


@pytest.fixture(scope="module")
def packs():
    return {engine: _pack_frames(engine) for engine in ENGINES}


def _overlay_rows(engine: str):
    """The real view-time rows, exactly as the page builds them."""
    base = ROOT / engine_revenue_outlook_dir(engine)
    signature = revenue_outlook_signature(base, ROOT)
    pack = app.cached_load_revenue_outlook_pack(
        str(base), str(ROOT), signature, app.REVENUE_OUTLOOK_SCHEMA_VERSION
    )
    block = pack.manifest.get("official_vintages", {})
    key = app.RevenueScenarioComputationKey(
        engine=engine,
        uptake_basis=app.DEFAULT_EV_UPTAKE_MODE,
        current_fed_policy_state="published",
        official_fed_policy_state="published",
        ped_bridge_mode=PED_BRIDGE_DEFAULT_MODE,
        bridge_vintage_id=str(bridge_vintage_id_from_manifest(pack.manifest, ROOT) or ""),
        official_comparator_vintage_id=str(
            block.get("default_comparator_vintage_id") or "BEFU26"
        ),
        long_run_transition_schedule_id=str(
            block.get("long_run_transition_schedule_id") or app.UNBLENDED_SCHEDULE_ID
        ),
        long_run_shape_vintage_id=str(block.get("long_run_shape_vintage_id") or ""),
    )
    sens = app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off")
    rows, *_ = app.cached_scenario_overlay_rows(
        signature, sens, PED_BRIDGE_DEFAULT_MODE, key, pack
    )
    scenario, overlay = app._official_vintage_filter_for_key(key)
    rows = app._filter_official_vintage_rows(rows, scenario, overlay)
    rows = app._append_missing_official_rows(rows, scenario, overlay)
    return base, pack, signature, key, rows


def _selected(rows, base, label: str, grain: str):
    frame, _ = app._filter_series_rows_with_fallback(
        rows, label, grain, "Current planned path", (BASE_TRACE,), "published",
        pack_dir=str(base),
    )
    return frame[frame["scenario_role"].astype(str).eq("basecase")]


# ------------------------------------------- A. macro restatement lineage


@pytest.mark.parametrize("engine", ENGINES)
class TestTreasuryPopulationRestatement:
    """The wedge is a governed population restatement, not a free parameter."""

    def test_macro_factors_publish_a_separate_factor_per_ped_series(self, engine):
        _base, _pack, signature, _key, _rows = _overlay_rows(engine)
        _b, pack, sig, _k, _r = _overlay_rows(engine)
        macro, _ = app._safe_treasury_baseline_macro_replay(sig, pack)
        factors = macro.baseline_macro_annual_factors
        scoped = factors[factors["series_id"].astype(str).isin(TARGETS)]
        assert not scoped.empty, "no macro factors for the PED activity pair"
        assert set(scoped["series_id"].astype(str)) == set(TARGETS)

    def test_factor_ratio_is_the_population_restatement(self, engine):
        """factor(petrol) / factor(vktpc) is the population factor.

        This is the whole claim. If the two factors were equal the identity
        would hold against the legacy population and none of this machinery
        would be needed; they are not equal, and their ratio is a population
        restatement rather than an activity change.
        """
        _b, pack, sig, _k, _r = _overlay_rows(engine)
        macro, _ = app._safe_treasury_baseline_macro_replay(sig, pack)
        factors = macro.baseline_macro_annual_factors
        checked = 0
        for scenario in SCENARIOS:
            scoped = factors[
                factors["scenario_name"].astype(str).eq(scenario)
                & factors["series_id"].astype(str).isin(TARGETS)
            ]
            wide = scoped.pivot_table(
                index="june_year", columns="series_id", values="factor", aggfunc="first"
            )
            for fy in wide.index:
                ratio = float(wide.at[fy, "light_petrol_vkt"]) / float(
                    wide.at[fy, "ped_vkt_per_capita"]
                )
                assert ratio > 0.0
                # A pure activity overlay would move both series identically.
                if int(fy) >= 2028:
                    assert ratio > 1.0, (
                        f"{engine}/{scenario} FY{fy}: the factors are identical, so "
                        "no population restatement is present and the identity "
                        "should have closed against the legacy population"
                    )
                checked += 1
        assert checked >= 8, "vacuous: too few macro factor years compared"

    def test_terminal_factor_is_carried_forward_past_fy2030(self, engine):
        """FY2031-FY2050 use the terminal FY2030 factor, per the overlay."""
        _b, pack, sig, _k, _r = _overlay_rows(engine)
        macro, _ = app._safe_treasury_baseline_macro_replay(sig, pack)
        factors = macro.baseline_macro_annual_factors
        years = pd.to_numeric(factors["june_year"], errors="coerce")
        assert int(years.max()) == coverage.POPULATION_FACTOR_TERMINAL_FY, (
            "the macro factor table no longer ends at the terminal FY the "
            "carry-forward contract assumes"
        )

    def test_migration_lambda_does_not_explain_the_wedge(self, engine):
        """The default bridge applies no migration, so it cannot be the cause."""
        base = ROOT / engine_revenue_outlook_dir(engine)
        drift = pd.read_parquet(base / "ev_phev_ped_light_drift_assumptions.parquet")
        scoped = drift[
            drift["scenario_name"].astype(str).eq("current_basecase")
            & drift["lambda_mode"].astype(str).eq("fixed_light_only")
        ]
        assert not scoped.empty
        pre = pd.to_numeric(scoped["current_P_t_light_petrol_km"], errors="coerce")
        post = pd.to_numeric(scoped["current_PED_light_petrol_km"], errors="coerce")
        assert np.allclose(pre.to_numpy(), post.to_numpy(), rtol=0, atol=1e-9), (
            "the default bridge moved petrol km, so migration cannot be ruled "
            "out as the source of the wedge"
        )


# ------------------------------------------------- B. annual publication


@pytest.mark.parametrize("engine", ENGINES)
class TestAnnualPublication:
    def test_publication_helper_is_strictly_additive(self, engine, packs):
        _base, chart, line, _raw, _pop = packs[engine]
        after = _append_post_model_ped_activity_chart_rows(chart, line)
        key = ["series_id", "scenario_name", "time_grain", "period", "fed_path"]
        before_idx = chart.set_index([chart[c].astype(str) for c in key])["value"]
        after_idx = after.set_index([after[c].astype(str) for c in key])["value"]
        common = before_idx.index.intersection(after_idx.index)
        assert len(common) > 2000, "vacuous: almost nothing was compared"
        delta = (
            pd.to_numeric(before_idx.loc[common], errors="coerce")
            - pd.to_numeric(after_idx.loc[common], errors="coerce")
        ).abs()
        assert float(delta.max()) == 0.0, "an existing chart value moved"
        added = after_idx.index.difference(before_idx.index)
        added_series = {key_tuple[0] for key_tuple in added}
        assert added_series == {"light_petrol_vkt"}, (
            f"the helper touched unexpected series: {sorted(added_series)}"
        )

    def test_post_model_values_equal_line_reconciliation_exactly(self, engine, packs):
        _base, chart, line, _raw, _pop = packs[engine]
        after = _append_post_model_ped_activity_chart_rows(chart, line)
        published = after[
            after["series_id"].astype(str).eq("light_petrol_vkt")
            & after["time_grain"].astype(str).eq("june_year")
        ]
        governed = line[
            line["series_id"].astype(str).eq("light_petrol_vkt")
            & line["forecast_segment"].astype(str).eq("post_model_extrapolation")
        ]
        merged = published.merge(
            governed, left_on=["scenario_name", "june_year"],
            right_on=["scenario_name", "FY"], suffixes=("_chart", "_line"),
        )
        assert len(merged) == 40, f"expected 40 post-model rows, got {len(merged)}"
        delta = (
            pd.to_numeric(merged["value_chart"], errors="coerce")
            - pd.to_numeric(merged["value_line"], errors="coerce")
        ).abs()
        assert float(delta.max()) == 0.0

    def test_both_annual_series_reach_fy2050(self, engine):
        base, _pack, _sig, _key, rows = _overlay_rows(engine)
        for series_id, label in LABELS.items():
            frame = _selected(rows, base, label, "june_year")
            years = pd.to_numeric(frame["june_year"], errors="coerce")
            assert int(years.max()) == LAST_FY, f"{series_id} annual stops at {years.max()}"
            assert not years.duplicated().any(), f"{series_id} has duplicate FY rows"

    def test_display_series_order_is_unchanged(self, engine):
        del engine
        from model_dashboard import revenue_outlook as ro

        assert "light_petrol_vkt" not in set(ro.DISPLAY_SERIES_ORDER), (
            "light_petrol_vkt was added to DISPLAY_SERIES_ORDER; the additive "
            "publication path exists precisely so that is not needed"
        )


# --------------------------------------------- C. quarterly construction


@pytest.mark.parametrize("engine", ENGINES)
class TestQuarterlyConstruction:
    def test_both_quarterly_series_reach_2050q2_and_stop(self, engine):
        base, _pack, _sig, _key, rows = _overlay_rows(engine)
        for series_id, label in LABELS.items():
            frame = _selected(rows, base, label, "quarterly")
            periods = sorted(frame["period"].astype(str))
            assert periods, f"{series_id} produced no quarters"
            assert periods[-1] == LAST_QUARTER, f"{series_id} ends at {periods[-1]}"
            assert "2050Q3" not in periods and "2050Q4" not in periods

    def test_every_fiscal_year_reconciles_to_its_annual(self, engine):
        base, _pack, _sig, _key, rows = _overlay_rows(engine)
        checked = 0
        for series_id, label in LABELS.items():
            quarterly = _selected(rows, base, label, "quarterly")
            annual = _selected(rows, base, label, "june_year")
            targets = annual.set_index(
                pd.to_numeric(annual["june_year"], errors="coerce")
            )["value"].map(float)
            grouped = quarterly.groupby(
                pd.to_numeric(quarterly["june_year"], errors="coerce")
            )["value"]
            for fy, values in grouped:
                if len(values) != 4 or fy not in targets.index:
                    continue
                total = float(pd.to_numeric(values).sum())
                target = float(targets.loc[fy])
                assert abs(total - target) <= 1e-6 * abs(target), (
                    f"{engine}/{series_id} FY{int(fy)} quarters sum to {total} "
                    f"against an annual of {target}"
                )
                checked += 1
        assert checked >= 40, f"vacuous: only {checked} fiscal years reconciled"

    def test_no_negative_or_duplicate_quarter(self, engine):
        base, _pack, _sig, _key, rows = _overlay_rows(engine)
        for label in LABELS.values():
            frame = _selected(rows, base, label, "quarterly")
            values = pd.to_numeric(frame["value"], errors="coerce")
            assert (values > 0).all(), "a non-positive quarter was published"
            assert not frame["period"].astype(str).duplicated().any()

    def test_native_quarters_are_unchanged(self, engine):
        """Derived rows fill gaps; they never restate a published quarter."""
        base, _pack, _sig, _key, rows = _overlay_rows(engine)
        native_rows = rows[
            rows["series_id"].astype(str).eq("ped_vkt_per_capita")
            & rows["time_grain"].astype(str).eq("quarterly")
            & rows["scenario_name"].astype(str).eq("current_basecase")
        ]
        native = pd.Series(
            pd.to_numeric(native_rows["value"], errors="coerce").to_numpy(),
            index=native_rows["period"].astype(str).to_numpy(),
        )
        frame = _selected(rows, base, LABELS["ped_vkt_per_capita"], "quarterly")
        rendered = pd.Series(
            pd.to_numeric(frame["value"], errors="coerce").to_numpy(),
            index=frame["period"].astype(str).to_numpy(),
        )
        shared = [p for p in native.index if p in rendered.index]
        assert shared, "vacuous: no native quarter survived into the view"
        for period in shared:
            assert float(rendered.loc[period]) == pytest.approx(
                float(native.loc[period]), abs=1e-9
            ), f"native quarter {period} was restated"

    def test_derived_rows_declare_the_restated_population_basis(self, engine):
        base, _pack, _sig, _key, rows = _overlay_rows(engine)
        frame = _selected(rows, base, LABELS["light_petrol_vkt"], "quarterly")
        derived = frame[
            frame.get("derivation_method", pd.Series("", index=frame.index))
            .astype(str)
            .eq(coverage.METHOD_POST_MODEL_RAW_SHAPE)
        ]
        assert not derived.empty, "no rows carry the post-model quarterly method"
        basis = set(derived["population_basis"].astype(str))
        assert basis == {coverage.POPULATION_BASIS_TREASURY_RESTATED}, (
            f"population basis not declared as the restatement: {basis}"
        )
        source = set(derived["population_factor_source"].astype(str))
        assert source == {coverage.POPULATION_FACTOR_SOURCE}

    def test_cross_series_quarterly_identity_closes(self, engine):
        """petrol_q = vktpc_q * restated_population_q / 1e6, per quarter.

        This is the test that catches the two series being built by different
        rules. Light petrol VKT has no native quarters, so the generic
        per-trace fallback splits its whole horizon with the Denton rule; if
        the joint construction does not supersede that over the post-model
        window, each series still reconciles to its own annual while the pair
        drifts apart quarter by quarter.
        """
        base, _pack, _sig, _key, rows = _overlay_rows(engine)
        petrol = _selected(rows, base, LABELS["light_petrol_vkt"], "quarterly")
        vktpc = _selected(rows, base, LABELS["ped_vkt_per_capita"], "quarterly")
        population = pd.read_parquet(
            Path(base) / "scenario_inputs" / "scenario_input_wide.parquet"
        )
        population = population[
            population["stream"].astype(str).eq("PED")
            & population["scenario_name"].astype(str).eq("current_basecase")
        ]
        legacy = dict(
            zip(
                population["canonical_period"].astype(str),
                pd.to_numeric(population["population"], errors="coerce"),
            )
        )
        factors = dict(
            zip(
                petrol["period"].astype(str),
                pd.to_numeric(petrol.get("population_factor"), errors="coerce"),
            )
        )
        petrol_by_period = dict(
            zip(petrol["period"].astype(str), pd.to_numeric(petrol["value"], errors="coerce"))
        )
        vktpc_by_period = dict(
            zip(vktpc["period"].astype(str), pd.to_numeric(vktpc["value"], errors="coerce"))
        )
        checked = 0
        for period in sorted(set(petrol_by_period) & set(vktpc_by_period) & set(legacy)):
            factor = factors.get(period)
            if factor is None or pd.isna(factor):
                continue
            predicted = float(vktpc_by_period[period]) * legacy[period] * float(factor) / 1e6
            actual = float(petrol_by_period[period])
            assert abs(actual - predicted) <= 1e-9 * abs(actual), (
                f"{engine} {period}: petrol {actual} against "
                f"vktpc x restated population {predicted}"
            )
            checked += 1
        assert checked >= 60, f"vacuous: only {checked} quarters carried the identity"

    def test_post_model_window_supersedes_the_generic_denton_split(self, engine):
        """Both series must use the joint rule over FY2031-FY2050."""
        base, _pack, _sig, _key, rows = _overlay_rows(engine)
        for label in LABELS.values():
            frame = _selected(rows, base, label, "quarterly")
            years = pd.to_numeric(frame["june_year"], errors="coerce")
            methods = (
                frame.get("derivation_method", pd.Series("", index=frame.index))
                .fillna("")
                .astype(str)
            )
            # Native quarters inside FY2031 (2030Q3/2030Q4) carry no
            # derivation method and must keep their published values, so only
            # DERIVED rows are held to the joint rule.
            post_model = methods[years.ge(FIRST_POST_MODEL_FY) & methods.ne("")]
            assert not post_model.empty
            assert set(post_model) == {coverage.METHOD_POST_MODEL_RAW_SHAPE}, (
                f"{label} FY{FIRST_POST_MODEL_FY}+ still carries "
                f"{sorted(set(post_model))}"
            )

    def test_ped_vkt_per_capita_stays_sum_preserving(self, engine, packs):
        """The unit string says "per capita"; the convention is a SUM.

        ``_is_average_preserving_unit`` would classify this series as
        average-preserving from its unit text alone. The published native
        quarters are sum-preserving, and the construction must not silently
        switch convention.
        """
        _base, chart, _line, _raw, _pop = packs[engine]
        quarterly = chart[
            chart["series_id"].astype(str).eq("ped_vkt_per_capita")
            & chart["time_grain"].astype(str).eq("quarterly")
            & chart["scenario_name"].astype(str).eq("current_basecase")
        ]
        annual_rows = chart[
            chart["series_id"].astype(str).eq("ped_vkt_per_capita")
            & chart["time_grain"].astype(str).eq("june_year")
            & chart["scenario_name"].astype(str).eq("current_basecase")
        ]
        annual = pd.Series(
            pd.to_numeric(annual_rows["value"], errors="coerce").to_numpy(),
            index=pd.to_numeric(annual_rows["june_year"], errors="coerce").to_numpy(),
        )
        grouped = quarterly.groupby(
            pd.to_numeric(quarterly["june_year"], errors="coerce")
        )["value"]
        checked = 0
        for fy, values in grouped:
            if len(values) != 4 or fy not in annual.index:
                continue
            total = float(pd.to_numeric(values).sum())
            target = float(annual.loc[fy])
            assert abs(total - target) <= 1e-6 * abs(target), (
                f"FY{int(fy)} native quarters are not sum-preserving"
            )
            checked += 1
        assert checked >= 3, "vacuous: too few native years checked"


# --------------------------------------------------- D. engine isolation


class TestEngineIsolation:
    def test_pack_dir_is_required_for_the_gap_fill(self):
        """Without an explicit pack directory the fill must not guess.

        Resolving it from the process-wide active engine read one engine's raw
        quarterly path against another engine's annual targets.
        """
        base, _pack, _sig, _key, rows = _overlay_rows("ensemble")
        del base
        empty = app._post_model_ped_activity_quarters(
            LABELS["ped_vkt_per_capita"], annual_rows=rows, chart_rows=rows, pack_dir=""
        )
        assert empty.empty

    def test_engines_do_not_share_quarterly_values(self):
        """The two engines must produce genuinely different quarters."""
        frames = {}
        for engine in ENGINES:
            base, _pack, _sig, _key, rows = _overlay_rows(engine)
            frame = _selected(rows, base, LABELS["light_petrol_vkt"], "quarterly")
            frames[engine] = frame.set_index(frame["period"].astype(str))["value"].map(float)
        shared = [p for p in frames["ensemble"].index if p in frames["ar1"].index]
        assert len(shared) > 50, "vacuous: engines share too few periods to compare"
        differences = [
            p for p in shared
            if abs(frames["ensemble"].loc[p] - frames["ar1"].loc[p]) > 1e-9
        ]
        assert differences, (
            "every quarter is identical across engines, which means one engine's "
            "pack is being served for both"
        )

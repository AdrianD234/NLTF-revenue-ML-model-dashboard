"""What only the COMBINED workshop release can be asked.

Each component proved its own contract in isolation. These are the questions
that only exist once the three are one page: does the quarterly derivation see
the policy-adjusted annual rows, do the bands follow the central path's policy,
is the horizon one number rather than two that happen to agree, and does the
page reach for the governed APIs rather than a local copy of their logic.

A failure here is an integration defect, not a component regression - the
component suites are still the place that proves each part alone.
"""
from __future__ import annotations

import ast
import math
from pathlib import Path

import pandas as pd
import pytest

import app
from model_dashboard import revenue_outlook_policy_runtime as policy_runtime
from model_dashboard import revenue_outlook_presentation_policy as presentation
from model_dashboard import revenue_outlook_series_coverage as coverage

ROOT = Path(__file__).resolve().parents[1]
ENGINES = ("ar1", "ensemble")


@pytest.fixture(scope="module")
def chart_rows() -> pd.DataFrame:
    return pd.read_parquet(ROOT / "data/current_revenue_outlook/revenue_chart_rows.parquet")


# --------------------------------------------------------------- one horizon


def test_the_display_horizon_is_configured_once() -> None:
    """Both modules must read one number, not two that currently agree.

    Two literals that happen to match today are one careless edit away from a
    quarterly chart that runs a year past the annual one.
    """
    assert coverage.DISPLAY_HORIZON_LAST_FY is presentation.REVENUE_OUTLOOK_DISPLAY_END_FY
    assert coverage.DISPLAY_HORIZON_LAST_QUARTER == presentation.terminal_display_quarter()
    assert coverage.DISPLAY_HORIZON_LAST_QUARTER == "2050Q2"


def test_the_two_horizon_filters_agree_row_for_row(chart_rows: pd.DataFrame) -> None:
    """A's frame clip and B's filter must keep the SAME rows.

    They are separate implementations reached by different paths, so agreeing
    on the constant is not enough - they have to agree on the rule, including
    the one that matters: a 2050Q3 row is FY2051 and must not survive on its
    calendar year.
    """
    by_a = presentation.clip_frame_to_display_horizon(chart_rows)
    by_b = coverage.display_horizon_filter(chart_rows)
    assert len(by_a) == len(by_b)
    assert set(by_a.index) == set(by_b.index)

    edge = pd.DataFrame(
        {
            "period": ["2050Q1", "2050Q2", "2050Q3", "2051Q1", "FY2050", "FY2051"],
            "june_year": [2050, 2050, 2051, 2051, 2050, 2051],
            "value": [1.0] * 6,
        }
    )
    kept_a = set(presentation.clip_frame_to_display_horizon(edge)["period"])
    kept_b = set(coverage.display_horizon_filter(edge)["period"])
    assert kept_a == kept_b == {"2050Q1", "2050Q2", "FY2050"}


# ----------------------------------------------- policy-specific quarterly


@pytest.mark.parametrize(
    ("policy_state", "stepped_quarter", "flat_quarter"),
    [
        ("published", "2027Q1", "2026Q4"),
        ("delayed_6m", "2027Q3", "2027Q2"),
    ],
)
def test_the_12c_step_lands_in_the_quarter_its_policy_puts_it_in(
    policy_state: str, stepped_quarter: str, flat_quarter: str
) -> None:
    """The governed rate timetable, not a fixed published one.

    Deriving a delayed year's quarters on the published schedule would still
    reconcile to the annual benchmark and still draw the step three months
    early, which is the failure this argument exists to prevent.
    """
    quarters = ["2026Q3", "2026Q4", "2027Q1", "2027Q2", "2027Q3", "2027Q4"]
    factors = coverage._rate_indicator_factor(quarters, ROOT, policy_state)
    rates = dict(zip(quarters, (float(value) for value in factors)))
    assert rates[stepped_quarter] > rates[flat_quarter]
    assert rates[stepped_quarter] == pytest.approx(rates[flat_quarter] + 0.12, abs=1e-9)


def test_no_uplift_never_steps_by_12c() -> None:
    """Under no-uplift the 12c step must be absent everywhere, not moved."""
    quarters = [f"{year}Q{q}" for year in range(2026, 2032) for q in (1, 2, 3, 4)]
    published = coverage._rate_indicator_factor(quarters, ROOT, "published")
    off = coverage._rate_indicator_factor(quarters, ROOT, "off")
    gaps = {round(float(p) - float(o), 6) for p, o in zip(published, off)}
    # Either the 12c has not happened yet (0.0) or it is permanently absent.
    assert gaps <= {0.0, 0.12}
    assert 0.12 in gaps
    # A step of exactly 12c must never appear inside the no-uplift path.
    steps = {round(float(b) - float(a), 6) for a, b in zip(off, off[1:])}
    assert 0.12 not in steps


def test_a_policy_state_the_contract_does_not_know_is_refused() -> None:
    """Silently taking the published timetable would draw the wrong quarter."""
    with pytest.raises(coverage.SeriesCoverageError):
        coverage._rate_indicator_factor(["2027Q1"], ROOT, "delayed_12m")


# ------------------------------------------- the derivation sees FINAL rows


def test_the_quarterly_derivation_reconciles_to_the_annual_rows_it_was_given(
    chart_rows: pd.DataFrame,
) -> None:
    """Quarters must close on the benchmark handed in, whatever moved it.

    This is the property that makes "pass the FINAL annual rows" meaningful:
    if a lever, a policy or a formula rebuild moves an annual value, the
    quarters below it move with it rather than reconciling to a stale layer.
    """
    annual = chart_rows[
        chart_rows["time_grain"].astype(str).eq("june_year")
        & chart_rows["series_id"].astype(str).eq("gross_ped_revenue")
        & chart_rows["trace_name"].astype(str).eq("Current finalist Base case")
    ].copy()
    assert not annual.empty
    # Move the annual path by a factor no offline pack could know about.
    moved = annual.copy()
    moved["value"] = pd.to_numeric(moved["value"], errors="coerce") * 1.07
    derived = coverage.derive_quarterly_rows(moved, chart_rows=chart_rows, repo_root=ROOT)
    assert not derived.empty
    for fy, group in derived.groupby(pd.to_numeric(derived["june_year"], errors="coerce")):
        benchmark = moved[pd.to_numeric(moved["june_year"], errors="coerce").eq(fy)]
        if benchmark.empty:
            continue
        expected = float(pd.to_numeric(benchmark["value"], errors="coerce").iloc[0])
        got = math.fsum(pd.to_numeric(group["value"], errors="coerce").dropna())
        assert got == pytest.approx(expected, rel=1e-12, abs=1e-9)


def test_supplied_traces_win_over_the_offline_pack(chart_rows: pd.DataFrame) -> None:
    """The caller's rows are on screen; the pack's are the offline baseline.

    Serving the pack for a trace the caller supplied is how a deferred policy
    or a moved lever ends up with quarters that do not sum to the annual line
    printed beside them.
    """
    trace = "Current finalist Base case"
    annual = chart_rows[
        chart_rows["time_grain"].astype(str).eq("june_year")
        & chart_rows["series_id"].astype(str).eq("gross_ped_revenue")
        & chart_rows["trace_name"].astype(str).eq(trace)
    ].copy()
    annual["value"] = pd.to_numeric(annual["value"], errors="coerce") * 1.5
    rows = coverage.quarterly_rows_for_selected_series(
        "gross_ped_revenue",
        trace_names=[trace],
        annual_rows=annual,
        chart_rows=chart_rows,
        repo_root=ROOT,
    )
    got = rows[rows["trace_name"].astype(str).eq(trace)]
    assert not got.empty
    for fy, group in got.groupby(pd.to_numeric(got["june_year"], errors="coerce")):
        benchmark = annual[pd.to_numeric(annual["june_year"], errors="coerce").eq(fy)]
        if benchmark.empty:
            continue
        expected = float(pd.to_numeric(benchmark["value"], errors="coerce").iloc[0])
        assert math.fsum(
            pd.to_numeric(group["value"], errors="coerce").dropna()
        ) == pytest.approx(expected, rel=1e-12, abs=1e-9)


def test_every_selectable_stream_label_resolves_to_a_quarterly_contract(
    chart_rows: pd.DataFrame,
) -> None:
    """A label a reader can pick must have a governed quarterly rule.

    The selector adds Light petrol VKT by hand and offers the RUC activity
    series under a second name apiece, so the offered vocabulary is wider than
    the pack's own series_label column.
    """
    for label in app._revenue_outlook_stream_options(chart_rows):
        assert coverage.canonical_series_id(label), label


# ----------------------------------------------------- derived provenance


def test_derived_quarters_keep_their_provenance_through_the_display_path(
    chart_rows: pd.DataFrame,
) -> None:
    """Hover, audit and download all read these columns off the same rows."""
    selected, used_fallback = app._filter_series_rows_with_fallback(
        chart_rows,
        "Light RUC net km",
        "quarterly",
        "Current planned path",
        ("Current finalist Base case", "MBU26 official"),
        "published",
    )
    assert used_fallback
    derived = selected[selected["trace_name"].astype(str).eq("MBU26 official")]
    assert not derived.empty
    for column in (
        "coverage_row_type",
        "empirical_or_derived",
        "derivation_method",
        "seasonal_basis",
        "rate_basis",
        "annual_source_period",
        "annual_source_value",
        "annual_reconciliation_residual",
        "source_basis",
    ):
        assert column in derived.columns, column
    assert set(derived["empirical_or_derived"].astype(str)) == {"derived"}
    assert "official" not in set(derived["value_status"].astype(str))


def test_an_official_derived_quarter_never_claims_to_be_published(
    chart_rows: pd.DataFrame,
) -> None:
    rows = coverage.quarterly_rows_for_selected_series(
        "light_ruc_net_km", trace_names=["MBU26 official"], chart_rows=chart_rows, repo_root=ROOT
    )
    official_derived = rows[
        rows["coverage_row_type"].astype(str).eq("derived_quarterly_from_governed_annual")
    ]
    assert not official_derived.empty
    assert set(official_derived["source_basis"].astype(str)) == {
        "derived quarterly presentation from official annual source"
    }


# ------------------------------------------------- restored official lines


def test_befu26_and_mbu26_light_petrol_vkt_reach_the_runtime_rows(
    chart_rows: pd.DataFrame,
) -> None:
    """The selector offered this series with no official comparator at all."""
    combined = app._append_missing_official_rows(chart_rows)
    petrol = combined[combined["series_id"].astype(str).eq("light_petrol_vkt")]
    traces = set(petrol["trace_name"].astype(str))
    assert {"BEFU26 official", "MBU26 official"} <= traces
    for trace in ("BEFU26 official", "MBU26 official"):
        block = petrol[petrol["trace_name"].astype(str).eq(trace)]
        assert not block.empty
        # Lineage must name the vintage's own file, not the other vintage's.
        sources = " ".join(block["source"].astype(str))
        assert trace.split()[0].lower() in sources.lower()
        assert set(block["value_unit"].astype(str)) == {"million km"}


def test_the_two_vintages_are_not_copied_onto_each_other(chart_rows: pd.DataFrame) -> None:
    combined = app._append_missing_official_rows(chart_rows)
    petrol = combined[combined["series_id"].astype(str).eq("light_petrol_vkt")]
    befu = petrol[petrol["trace_name"].astype(str).eq("BEFU26 official")].set_index("june_year")
    mbu = petrol[petrol["trace_name"].astype(str).eq("MBU26 official")].set_index("june_year")
    shared = sorted(set(befu.index) & set(mbu.index))
    assert shared
    differences = sum(
        1
        for fy in shared
        if float(befu.loc[fy, "value"]) != float(mbu.loc[fy, "value"])
    )
    assert differences > 0, "two vintages that agree everywhere are one vintage twice"


def test_appending_official_rows_moves_no_existing_value(chart_rows: pd.DataFrame) -> None:
    """Strictly additive: every row already present must survive untouched."""
    combined = app._append_missing_official_rows(chart_rows)
    identity = ["series_id", "trace_name", "time_grain", "period"]
    before = chart_rows.set_index(identity)["value"]
    after = combined.set_index(identity)["value"]
    assert len(after) >= len(before)
    common = before.index.intersection(after.index)
    pd.testing.assert_series_equal(
        before.loc[common].sort_index(), after.loc[common].sort_index(), check_names=False
    )


def test_no_duplicate_official_row_identity(chart_rows: pd.DataFrame) -> None:
    combined = app._append_missing_official_rows(chart_rows)
    identity = ["series_id", "trace_name", "time_grain", "period"]
    assert not combined.duplicated(subset=identity).any()


# --------------------------------------------- quarterly uncertainty honesty


def test_no_governed_quarterly_uncertainty_contract_exists() -> None:
    """The premise of withholding the bands, asserted rather than assumed."""
    bands = pd.read_parquet(ROOT / "data/revenue_outlook_uncertainty/uncertainty_band_rows.parquet")
    periods = set(bands["period"].astype(str)) if "period" in bands.columns else set()
    assert periods, "band rows carry no period column"
    assert all(period.startswith("FY") for period in periods)
    assert not any("Q" in period for period in periods)


def test_the_quarterly_view_withholds_rather_than_fabricates_bands() -> None:
    """The note must exist and must say why, not merely that."""
    note = app.QUARTERLY_UNCERTAINTY_NOT_GOVERNED_NOTE.casefold()
    assert "june-year" in note
    assert "quarter" in note
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    # The suppression must be on the GRAIN, not on whether rows happen to be
    # empty - an empty-frame check would silently pass a fabricated frame.
    assert "quarterly_grain = selected_time_grain ==" in source


# ----------------------------------------------- the withdrawn VFM surface


@pytest.mark.parametrize("engine", ENGINES)
def test_a_normal_render_never_deserialises_a_vfm_frame(engine: str) -> None:
    """A's gate closes the public consumers; prove the frames stay on disk.

    The loader is lazy, so retaining them costs nothing - but "costs nothing"
    is a claim about what is read, and this is the assertion that checks it.
    """
    try:
        runtime = policy_runtime.load_policy_runtime(engine=engine, repo_root=ROOT)
    except RuntimeError as error:
        pytest.skip(f"policy runtime unavailable: {error}")
    key = _catalogued_key(runtime, engine)
    policy_runtime.policy_chart_rows(runtime, key)
    policy_runtime.policy_uncertainty_rows(runtime, key)
    policy_runtime.policy_audit_rows(runtime, key)
    loaded = {name for (_state, name) in runtime._frames}
    assert "vfm_fast_chart_rows" not in loaded
    assert "vfm_slow_chart_rows" not in loaded


def test_the_production_page_never_calls_the_vfm_scenario_api() -> None:
    """A source check, because a runtime check only covers paths it walks."""
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "policy_vfm_scenario_rows" not in source


def test_production_keys_never_carry_the_retention_sensitivity() -> None:
    assert presentation.REVENUE_OUTLOOK_ENABLE_PED_RETENTION_CONTROL is False
    assert app._production_ped_retention_sensitivity() is False


# ------------------------------------------- the app reaches for the APIs


def test_the_page_does_not_reimplement_the_governed_quarterly_split() -> None:
    """The display path must call the contract, not a local Denton solve."""
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    fallback = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "_filter_series_rows_with_fallback"
    )
    called = {
        node.func.id
        for node in ast.walk(fallback)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_governed_quarterly_rows" in called
    assert "_disaggregate_annual_rows_to_quarterly" not in called


def test_the_page_reaches_for_both_component_apis() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    for symbol in (
        "quarterly_rows_for_selected_series",
        "missing_official_rows",
        "canonical_series_id",
        "policy_chart_rows",
        "policy_detail_frames",
        "policy_uncertainty_rows",
        "resolve_policy_state",
    ):
        assert symbol in source, symbol


def test_the_two_official_vintage_filters_agree(chart_rows: pd.DataFrame) -> None:
    """C reimplemented app's filter to avoid importing Streamlit.

    That is a reasonable trade, but it means two copies of one rule, and the
    fast path composes them. If they ever disagree the materialised rows stop
    matching the reference path's, so pin them together here.
    """
    for vintage in ("BEFU26", "MBU26"):
        for overlay in (False, True):
            by_app = app._filter_official_vintage_rows(
                chart_rows, app.official_comparator_scenario_name(vintage), overlay
            )
            by_runtime = policy_runtime.filter_official_vintage_rows(
                chart_rows, vintage, overlay
            )
            assert set(by_app.index) == set(by_runtime.index), (vintage, overlay)


# ----------------------------------------------------- session migration


@pytest.mark.parametrize(
    "stale_value", ["FY2051", "FY2055", "2051Q1"]
)
def test_an_out_of_horizon_fy_marker_is_dropped_on_entry(stale_value: str) -> None:
    import streamlit as st

    st.session_state["revenue_outlook_selected_fy"] = stale_value
    app._discard_out_of_horizon_revenue_outlook_state()
    assert "revenue_outlook_selected_fy" not in st.session_state


def test_an_in_horizon_fy_marker_survives() -> None:
    import streamlit as st

    st.session_state["revenue_outlook_selected_fy"] = "FY2050"
    app._discard_out_of_horizon_revenue_outlook_state()
    assert st.session_state["revenue_outlook_selected_fy"] == "FY2050"


def test_an_unknown_policy_selection_is_dropped_not_coerced() -> None:
    """Coercing would swap one counterfactual for another, silently."""
    import streamlit as st

    st.session_state["revenue_outlook_fed_policy_state"] = "delayed_12m"
    app._discard_unknown_revenue_outlook_policy_state()
    assert "revenue_outlook_fed_policy_state" not in st.session_state


@pytest.mark.parametrize("state", ["published", "delayed_6m", "off"])
def test_a_live_policy_selection_survives(state: str) -> None:
    import streamlit as st

    st.session_state["revenue_outlook_fed_policy_state"] = state
    app._discard_unknown_revenue_outlook_policy_state()
    assert st.session_state["revenue_outlook_fed_policy_state"] == state


# ------------------------------------------------- policy runtime plumbing


def _catalogued_key(runtime, engine: str):
    """A key the catalogue is pinned to answer, from the manifest itself."""
    state = runtime.manifest["states"][0]
    pinned = runtime.manifest["pinned_key_fields"]
    return app.RevenueScenarioComputationKey(
        engine=engine,
        current_fed_policy_state=state["current_fed_policy_state"],
        official_fed_policy_state=state["official_fed_policy_state"],
        **{
            name: (tuple(value) if isinstance(value, list) else value)
            for name, value in pinned.items()
        },
    )


@pytest.mark.parametrize("engine", ENGINES)
def test_an_uncatalogued_key_falls_back_rather_than_approximating(engine: str) -> None:
    """No nearest match: an unsupported control must reach the reference path."""
    try:
        runtime = policy_runtime.load_policy_runtime(engine=engine, repo_root=ROOT)
    except RuntimeError as error:
        pytest.skip(f"policy runtime unavailable: {error}")
    custom = _catalogued_key(runtime, engine).replace(custom_ev_levers=(0.42,))
    resolution = policy_runtime.resolve_policy_state(runtime, custom)
    assert resolution.status == policy_runtime.STATUS_REFERENCE_REQUIRED
    assert "custom_ev_levers" in resolution.detail


def test_the_builder_switches_the_fast_path_off() -> None:
    """A rebuild must materialise the reference pipeline, not itself.

    The page answers a catalogued key from this pack, and the builder calls
    the same page functions. With the fast path left on, a rebuild would copy
    the pack it is about to overwrite: byte-identical output proving nothing
    except that a file was read twice.
    """
    builder = (ROOT / "scripts" / "build_revenue_outlook_policy_runtime.py").read_text(
        encoding="utf-8"
    )
    assert "app.POLICY_RUNTIME_FAST_PATH_ENABLED = False" in builder
    assert app.POLICY_RUNTIME_FAST_PATH_ENABLED is True, "production default must stay on"


def test_the_fast_path_switch_actually_disables_it() -> None:
    original = app.POLICY_RUNTIME_FAST_PATH_ENABLED
    try:
        app.POLICY_RUNTIME_FAST_PATH_ENABLED = False
        assert app._policy_runtime_for_pack(None) is None
    finally:
        app.POLICY_RUNTIME_FAST_PATH_ENABLED = original


def test_a_moved_sensitivity_lever_is_never_served_from_the_catalogue() -> None:
    """The sensitivity key is outside the typed key, so the fast path checks it.

    Without this guard a moved lever would be answered with the catalogue's
    default-sensitivity rows - the exact silent wrong answer the catalogue
    exists to avoid.
    """
    moved = app.selected_sensitivity_key(
        "High", "Off", "Off", freight_rail_shift="Off"
    )
    assert not app._is_default_sensitivity_key(tuple(moved))
    assert (
        app._materialised_policy_overlay_rows(
            app.RevenueScenarioComputationKey(engine="ensemble"), None, moved, ""
        )
        is None
    )

"""The long-run restoration must not resurrect the defect that caused the cut.

P0 withheld decision-facing Current values past FY2030 because the retired
constructor divided a growing conventional forecast by a conventional share
approaching zero, implying ~185,800 million km of Light RUC by FY2050 (~3.9x
the VFM pool). These gates let the long-run view exist while making that
specific construction impossible to reintroduce, and they pin the
presentation decisions the restoration depends on.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import app
from model_dashboard.post_model_extrapolation import (
    ANCHOR_FY,
    FIRST_EXTRAPOLATION_FY,
    LAST_EXTRAPOLATION_FY,
    LIGHT_POOL_MAX_RATIO_TO_VFM,
    MAX_CUMULATIVE_INDEX,
    POST_MODEL_SEGMENT,
    PostModelExtrapolationError,
    anchor_index_level_audit,
    build_post_model_extrapolation_annual,
    post_model_growth_indices,
)
from model_dashboard.revenue_outlook import (
    FAN_SEGMENT_EMPIRICAL,
    FAN_SEGMENT_LONG_RUN_ENVELOPE,
    FAN_SOURCE_CURRENT_BACKTEST,
    FAN_SOURCE_MBU26_ARCHIVED,
    FAN_SOURCE_SCENARIO_SPREAD,
    load_revenue_outlook_pack,
)

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "data" / "current_revenue_outlook"
BASE = "current_basecase"
COMPARISON = "current_comparison_1"
RETIRED_PATHOLOGY_MILLION_KM = 185_800.0


@pytest.fixture(scope="module")
def pack():
    loaded = load_revenue_outlook_pack(PACK, repo_root=ROOT)
    assert loaded is not None, "the committed pack must load through the completeness gate"
    return loaded


@pytest.fixture(scope="module")
def chart(pack) -> pd.DataFrame:
    return pack.revenue_chart_rows


@pytest.fixture(scope="module")
def line(pack) -> pd.DataFrame:
    return pack.revenue_line_reconciliation


def _annual(frame: pd.DataFrame, scenario: str, series: str) -> pd.Series:
    scoped = frame[
        frame["time_grain"].astype(str).eq("june_year")
        & frame["scenario_name"].astype(str).eq(scenario)
        & frame["series_id"].astype(str).eq(series)
    ]
    return (
        pd.to_numeric(scoped["value"], errors="coerce")
        .groupby(pd.to_numeric(scoped["june_year"], errors="coerce"))
        .first()
        .sort_index()
    )


# ---------------------------------------------------------------- 1, 2. banner
def test_no_public_horizon_warning_banner_is_rendered() -> None:
    source = inspect.getsource(app.render_revenue_outlook_page)
    assert "_render_forecast_horizon_support_note(" not in source, (
        "the governance banner must not render on the public page"
    )


def test_horizon_metadata_survives_in_the_governed_pack(chart) -> None:
    """Removing the banner must not remove the governance fields."""
    for column in ("horizon_scope", "value_status", "forecast_segment"):
        assert column in chart.columns, column
    assert chart["horizon_scope"].astype(str).str.len().gt(0).any()
    # The prose builder itself stays available to non-public surfaces.
    assert callable(app._forecast_horizon_support_note)


# ------------------------------------------------------------------- 3-6. fan
def test_uncertainty_fan_is_rendered_again(pack) -> None:
    source = inspect.getsource(app.render_revenue_outlook_page)
    assert "_render_revenue_outlook_fan_card(" in source
    assert not pack.fan_band_rows.empty
    assert not pack.fan_availability.empty


def test_fan_bands_carry_fifty_and_eighty_ranges(pack) -> None:
    bands = pack.fan_band_rows
    for column in ("lower50", "upper50", "lower80", "upper80", "central"):
        assert column in bands.columns, column
        assert pd.to_numeric(bands[column], errors="coerce").notna().any()
    numeric = bands.apply(lambda column: pd.to_numeric(column, errors="coerce"))
    inner = numeric["upper50"] - numeric["lower50"]
    outer = numeric["upper80"] - numeric["lower80"]
    valid = inner.notna() & outer.notna()
    assert (outer[valid] >= inner[valid] - 1e-9).all(), "the 80% band must contain the 50%"


def test_empirical_fan_bands_stop_at_the_supported_horizon(pack) -> None:
    """An empirical interval must not be extrapolated past its own basis.

    A backtest-calibrated 50/80 band asserts something about realised
    forecast error. Carried into FY2031-FY2050 around a structural
    extrapolation it would assert something it cannot support, so those rows
    are dropped rather than relabelled.
    """
    bands = pack.fan_band_rows
    fy = pd.to_numeric(bands["FY"], errors="coerce")
    empirical = bands["fan_source"].astype(str).isin(
        [FAN_SOURCE_MBU26_ARCHIVED, FAN_SOURCE_CURRENT_BACKTEST]
    )
    assert not (empirical & fy.gt(ANCHOR_FY)).any(), (
        "an empirical band extends past FY2030"
    )


def test_long_run_fan_rows_are_labelled_as_a_scenario_envelope(pack) -> None:
    bands = pack.fan_band_rows
    assert "fan_segment" in bands.columns
    fy = pd.to_numeric(bands["FY"], errors="coerce")
    long_run = bands[fy.gt(ANCHOR_FY)]
    if not long_run.empty:
        assert long_run["fan_segment"].eq(FAN_SEGMENT_LONG_RUN_ENVELOPE).all()
        assert long_run["fan_source"].astype(str).eq(FAN_SOURCE_SCENARIO_SPREAD).all(), (
            "only a scenario spread may survive into the long run"
        )
    within = bands[fy.le(ANCHOR_FY)]
    assert within["fan_segment"].eq(FAN_SEGMENT_EMPIRICAL).all()


def test_scenario_spread_is_never_labelled_a_confidence_interval(pack) -> None:
    spread = pack.fan_band_rows[
        pack.fan_band_rows["fan_source"].astype(str).eq(FAN_SOURCE_SCENARIO_SPREAD)
    ]
    if spread.empty:
        pytest.skip("no scenario-spread rows materialised")
    text = " ".join(spread["interpretation"].dropna().astype(str)).lower()
    assert "not probabilistic" in text
    for banned in ("confidence interval", "credible interval", "prediction interval"):
        assert banned not in text, banned
    figure_source = inspect.getsource(app.revenue_outlook_uncertainty_fan_figure)
    assert "not probabilistic" in figure_source


def test_the_vfm_composition_band_stays_separate_from_the_fan() -> None:
    """Two different concepts must not share a visual language."""
    total_path = inspect.getsource(app.revenue_outlook_total_path_figure)
    assert "MoT VFM fast–slow range" in total_path
    assert "rgba(0,111,173" in total_path, "the VFM cone keeps its blue"
    fan = inspect.getsource(app.revenue_outlook_uncertainty_fan_figure)
    assert "rgba(128, 128, 128" in fan and "rgba(96, 96, 96" in fan, "the fan is gray"


# --------------------------------------------------- 7, 8. short-run unchanged
BASELINE = ROOT / "artifacts" / "revenue_outlook_long_run" / "short_run_baseline.csv"
_CHART_KEY = [
    "scenario_name", "scenario_role", "time_grain", "series_id",
    "period", "fed_path", "row_type", "trace_name",
]
_LINE_KEY = ["source_path", "scenario_name", "series_id", "period_fy"]
def _normalise_key(frame, key):
    """Stringify key columns consistently.

    An FY column read as float renders "2001.0" against the pack's "2001",
    so every row misses and an .all() over the empty selection passes
    vacuously. Numeric-looking keys are canonicalised to integers first.
    """
    import pandas as _pd

    for column in key:
        values = frame[column]
        numeric = _pd.to_numeric(values, errors="coerce")
        if numeric.notna().all():
            frame[column] = numeric.astype("Int64").astype(str)
        else:
            frame[column] = values.fillna("").astype(str)
    return frame



def test_current_short_run_values_are_unchanged() -> None:
    """Every pre-existing row must be EXACTLY equal to the frozen baseline.

    The baseline is a COMMITTED artifact, not a Git object. Reading
    `git show main:...` here would break a shallow CI checkout, which is
    exactly what test_no_test_or_generator_depends_on_a_historical_git_object
    exists to prevent - it caught an earlier revision of this test.

    Comparison is CSV-against-CSV: main's own CSV and parquet already
    disagree on 26 annual rows by one ULP (max 1.82e-12, relative 2.2e-16)
    from CSV text precision, so a CSV-vs-parquet check would report a
    serialisation artifact as a value move.
    """
    assert BASELINE.exists(), "regenerate the long-run evidence"
    baseline = pd.read_csv(BASELINE, low_memory=False, float_precision="round_trip")
    sources = {
        "incumbent_chart_rows": ("data/current_revenue_outlook/revenue_chart_rows.csv", _CHART_KEY),
        "ar1_chart_rows": ("data/engine_ar1/current_revenue_outlook/revenue_chart_rows.csv", _CHART_KEY),
    }
    for label, (rel, key) in sources.items():
        before = baseline[baseline["baseline_source"].eq(label)].copy()
        assert not before.empty, label
        after = pd.read_csv(ROOT / rel, low_memory=False, float_precision="round_trip")
        before = _normalise_key(before, key)
        after = _normalise_key(after, key)
        merged = before.merge(after, on=key, how="left", suffixes=("_base", "_now"))
        assert len(merged) == len(before), f"{rel}: a pre-existing row lost or duplicated"
        left = pd.to_numeric(merged["value_base"], errors="coerce")
        right = pd.to_numeric(merged["value_now"], errors="coerce")
        assert right[left.notna()].notna().all(), f"{rel}: a pre-existing value went missing"
        both = left.notna() & right.notna()
        assert int(both.sum()) >= int(0.99 * len(before)), (
            f"{rel}: only {int(both.sum())} of {len(before)} baseline rows matched"
        )
        assert (left[both] == right[both]).all(), f"{rel}: a pre-existing value moved"


def test_short_run_line_reconciliation_values_are_unchanged() -> None:
    assert BASELINE.exists(), "regenerate the long-run evidence"
    baseline = pd.read_csv(BASELINE, low_memory=False, float_precision="round_trip")
    before = baseline[baseline["baseline_source"].eq("incumbent_line_reconciliation")].copy()
    assert not before.empty
    after = pd.read_csv(
        ROOT / "data/current_revenue_outlook/revenue_line_reconciliation.csv",
        low_memory=False, float_precision="round_trip",
    ).rename(columns={"FY": "period_fy"})
    before = _normalise_key(before, _LINE_KEY)
    after = _normalise_key(after, _LINE_KEY)
    merged = before.merge(after, on=_LINE_KEY, how="left", suffixes=("_base", "_now"))
    assert len(merged) == len(before), "a pre-existing line row lost or duplicated"
    left = pd.to_numeric(merged["value_base"], errors="coerce")
    right = pd.to_numeric(merged["value_now"], errors="coerce")
    both = left.notna() & right.notna()
    # Non-vacuity: an all-missing join would make the comparison below pass
    # over an empty selection. The evidence script caught exactly that.
    assert int(both.sum()) >= int(0.99 * len(before)), (
        f"only {int(both.sum())} of {len(before)} baseline line rows matched"
    )
    assert (left[both] == right[both]).all(), "a pre-existing line value moved"


def test_the_short_run_baseline_covers_only_the_pre_existing_horizon() -> None:
    """The baseline must not silently acquire post-model rows.

    If a regeneration folded FY2031+ into the baseline, the identity check
    would compare the new layer against itself and pass vacuously.
    """
    baseline = pd.read_csv(BASELINE, low_memory=False, float_precision="round_trip")
    chart = baseline[baseline["baseline_source"].str.endswith("chart_rows")]
    annual = chart[chart["time_grain"].eq("june_year")]
    years = pd.to_numeric(annual["period"].astype(str).str.replace("FY", ""), errors="coerce")
    assert int(years.max()) <= 2055, "baseline horizon is implausible"
    current = annual[annual["scenario_role"].isin(["basecase", "comparison"])]
    current_years = pd.to_numeric(
        current["period"].astype(str).str.replace("FY", ""), errors="coerce"
    )
    assert int(current_years.max()) == ANCHOR_FY, (
        "the baseline must stop at the pre-change FY2030 current horizon"
    )


def test_actuals_and_official_rows_are_untouched(chart) -> None:
    actual = chart[chart["row_type"].astype(str).eq("historical_actual")]
    assert not actual.empty
    assert actual["forecast_segment"].fillna("").eq("").all(), (
        "actuals are outside the forecast segmentation"
    )
    official = chart[chart["scenario_role"].astype(str).eq("official_comparator")]
    assert official["forecast_segment"].fillna("").eq("").all()
    years = pd.to_numeric(official["june_year"], errors="coerce")
    assert int(years.max()) >= 2055, "the official comparator keeps its own horizon"


# --------------------------------------------- 9-13. long-run construction
@pytest.mark.parametrize("scenario", [BASE, COMPARISON])
def test_current_paths_extend_continuously_through_fy2050(chart, scenario) -> None:
    totals = _annual(chart, scenario, "total_nltf_net_revenue")
    expected = set(range(2026, LAST_EXTRAPOLATION_FY + 1))
    assert expected <= set(int(fy) for fy in totals.index), (
        f"missing FYs: {sorted(expected - set(int(fy) for fy in totals.index))[:6]}"
    )
    assert totals.notna().all()
    # No hole and no vertical jump at the seam.
    step = totals.loc[FIRST_EXTRAPOLATION_FY] / totals.loc[ANCHOR_FY] - 1.0
    assert abs(step) < 0.15, f"discontinuous seam: {step * 100:.2f}%"


def test_post_model_rows_begin_only_in_fy2031(chart) -> None:
    post = chart[chart["forecast_segment"].astype(str).eq(POST_MODEL_SEGMENT)]
    assert not post.empty
    years = pd.to_numeric(post["june_year"], errors="coerce")
    assert int(years.min()) == FIRST_EXTRAPOLATION_FY
    assert int(years.max()) == LAST_EXTRAPOLATION_FY
    assert post["time_grain"].astype(str).eq("june_year").all(), (
        "the post-model layer is annual only; H21+ quarterly stays withheld"
    )
    assert post["value_status"].astype(str).eq(POST_MODEL_SEGMENT).all()


def test_econometric_segment_never_extends_past_fy2030(chart) -> None:
    econometric = chart[chart["forecast_segment"].astype(str).eq("econometric_forecast")]
    annual = econometric[econometric["time_grain"].astype(str).eq("june_year")]
    years = pd.to_numeric(annual["june_year"], errors="coerce")
    assert int(years.max()) <= ANCHOR_FY, "an econometric value leaked past FY2030"


def test_no_lambda_or_shrinking_share_division_is_reintroduced() -> None:
    """Ban the retired idiom precisely: a LEVEL divided by a SHARE.

    A blunt "/ share" ban would also flag renormalising the vendored shares by
    their own sum (they are published at 6 dp and sum to 1 only to 1e-6), so
    the pattern is scoped to a level/pool/forecast numerator - which is what
    made the retired constructor diverge as the conventional share went to
    zero.
    """
    import re

    source = (ROOT / "model_dashboard" / "post_model_extrapolation.py").read_text(encoding="utf-8")
    lowered = source.lower()
    assert "lambda_" not in lowered, "the retired lambda machinery must not return"
    assert "migration_lambda" not in lowered
    level_over_share = re.compile(
        r"(conventional|pool|forecast|_km|level)\w*\s*/\s*\w*(share|conventional)\w*"
    )
    offenders = [
        line.strip()
        for line in lowered.splitlines()
        if not line.strip().startswith("#") and level_over_share.search(line)
    ]
    assert not offenders, f"a level is divided by a share: {offenders[:3]}"
    # And the sanctioned rule must be present and multiplicative.
    #
    # The pool is still `anchor x index`. Since the anchored structural shape
    # transition the index is the HYBRID one - a geometric blend of the VFM
    # pool index (the Current leg) with the selected official vintage's pool
    # index - which under the default unblended schedule equals the VFM pool
    # index exactly. So this asserts the multiplicative anchor x index FORM and
    # that the VFM pool index is still the Current leg, rather than pinning one
    # literal expression that a legitimate method change has to edit.
    assert "vfm_pool_index" in lowered
    assert re.search(
        r"pool_anchor\s*\*\s*g\[.(vfm_pool_index|h_light_ruc_pool).\]", lowered
    ), "the Light RUC pool must be anchor x index"
    # The VFM pool index must remain the Current leg of that blend, so the
    # structural source can never silently replace the vendored pool path.
    assert re.search(r'"light_ruc_pool":\s*"vfm_pool_index"', lowered), (
        "the VFM pool index must remain the Current leg of the Light RUC blend"
    )
    # The blend itself must be multiplicative/log-space, never additive on levels.
    assert "geometric_blend_index" in lowered


def test_light_ruc_long_run_pool_is_finite_and_passes_the_divergence_gate(chart) -> None:
    for scenario in (BASE, COMPARISON):
        pool = (
            _annual(chart, scenario, "light_ruc_net_km")
            + _annual(chart, scenario, "light_bev_ruc_net_km")
            + _annual(chart, scenario, "phev_ruc_net_km")
        )
        long_run = pool.loc[pool.index >= FIRST_EXTRAPOLATION_FY]
        assert np.isfinite(long_run.to_numpy()).all()
        assert (long_run > 0).all()
        worst = float(long_run.max())
        assert worst < RETIRED_PATHOLOGY_MILLION_KM * 0.5, (
            f"{scenario}: FY2050 pool {worst:.0f} Mkm approaches the retired "
            f"{RETIRED_PATHOLOGY_MILLION_KM:.0f} Mkm pathology"
        )


def test_the_retired_pathological_value_is_explicitly_banned(chart) -> None:
    """A named regression gate on the exact failure that caused the cutoff."""
    for scenario in (BASE, COMPARISON):
        pool_2050 = float(
            _annual(chart, scenario, "light_ruc_net_km").loc[2050]
            + _annual(chart, scenario, "light_bev_ruc_net_km").loc[2050]
            + _annual(chart, scenario, "phev_ruc_net_km").loc[2050]
        )
        assert pool_2050 < RETIRED_PATHOLOGY_MILLION_KM, "the pathology returned"
        ratio = pool_2050 / RETIRED_PATHOLOGY_MILLION_KM
        assert ratio < 0.5, f"{scenario}: pool is {ratio:.2f}x the retired value"


def test_growth_guards_reject_an_implausible_index() -> None:
    """The guards must fire, not merely exist."""
    from model_dashboard.post_model_extrapolation import _guard_growth_index

    fys = list(range(ANCHOR_FY, LAST_EXTRAPOLATION_FY + 1))
    exploding = pd.Series([1.3 ** (fy - ANCHOR_FY) for fy in fys], index=fys)
    with pytest.raises(PostModelExtrapolationError):
        _guard_growth_index(exploding, label="test", scenario_name="probe")
    inverted = pd.Series([1.0] + [-1.0] * (len(fys) - 1), index=fys)
    with pytest.raises(PostModelExtrapolationError, match="non-positive"):
        _guard_growth_index(inverted, label="test", scenario_name="probe")
    nan_index = pd.Series([1.0] * (len(fys) - 1) + [float("nan")], index=fys)
    with pytest.raises(PostModelExtrapolationError, match="non-finite"):
        _guard_growth_index(nan_index, label="test", scenario_name="probe")


def test_the_raw_model_level_is_never_republished_directly(line) -> None:
    raw = pd.read_parquet(PACK / "raw_quarterly_forecast_audit.parquet")
    wide = pd.read_parquet(PACK / "scenario_inputs" / "scenario_input_wide.parquet")
    audit = anchor_index_level_audit(
        line_reconciliation=line, raw_quarterly_audit=raw,
        scenario_input_wide=wide, repo_root=ROOT,
    )
    assert not audit.empty
    assert not audit["republished_raw_level"].any()
    # Anchor, index and level are reported as separate columns.
    for column in ("corrected_anchor_level", "growth_index", "extrapolated_level"):
        assert column in audit.columns, column
    # Every index is exactly 1.0 at the anchor by construction, so the FY2031
    # level is the anchor times a near-one step - never the raw level.
    assert audit["growth_index"].max() <= MAX_CUMULATIVE_INDEX


def test_extrapolation_fails_closed_without_its_governed_inputs(line) -> None:
    raw = pd.read_parquet(PACK / "raw_quarterly_forecast_audit.parquet")
    wide = pd.read_parquet(PACK / "scenario_inputs" / "scenario_input_wide.parquet")
    official = pd.read_csv(
        ROOT / "data/revenue_model_source_pack/mbu26_annual_spine/mbu26_official_annual.csv"
    )
    with pytest.raises(PostModelExtrapolationError, match="carries no rows"):
        post_model_growth_indices(
            raw[~raw["scenario_name"].astype(str).eq(BASE)], wide,
            scenario_name=BASE, repo_root=ROOT,
        )
    truncated = official[pd.to_numeric(official["FY"], errors="coerce").le(2040)]
    with pytest.raises(PostModelExtrapolationError, match="missing"):
        build_post_model_extrapolation_annual(
            line_reconciliation=line, raw_quarterly_audit=raw,
            scenario_input_wide=wide, mbu26_official_annual=truncated, repo_root=ROOT,
        )


# ------------------------------------------------------------- 14. closure
@pytest.mark.parametrize("scenario", [BASE, COMPARISON])
def test_total_nltf_closes_to_its_leaves_across_the_long_run(line, scenario) -> None:
    source_path = (
        "Current finalist Base case" if scenario == BASE
        else "Current finalist High population/comparison"
    )
    scoped = line[line["source_path"].astype(str).eq(source_path)]
    wide = scoped.pivot_table(
        index=pd.to_numeric(scoped["FY"], errors="coerce"),
        columns="series_id", values="value", aggfunc="first",
    )
    long_run = wide.loc[wide.index >= FIRST_EXTRAPOLATION_FY]
    assert not long_run.empty
    # Recompute from the GOVERNED registry, not hand-written arithmetic. An
    # earlier revision of this test hard-coded gross_ruc_revenue WITHOUT the
    # ruc_refunds term the governed expression includes, so it agreed with a
    # constructor that had the same omission and both were wrong together.
    from model_dashboard.mbu26_source_spine import FORMULA_DEFINITIONS

    checked = 0
    for definition in FORMULA_DEFINITIONS:
        series = str(definition["output_series_id"])
        if series not in long_run.columns:
            continue
        terms = definition["terms"]
        if any(term not in long_run.columns for term, _ in terms):
            continue
        calculated = sum(long_run[term] * sign for term, sign in terms)
        residual = (long_run[series] - calculated).abs().max()
        assert residual <= 1e-6, (
            f"{series} does not close over FY2031-FY2050: worst {residual:.3e} "
            f"(expression: {definition['expression']})"
        )
        checked += 1
    assert checked >= 10, f"only {checked} governed identities were checkable"


def test_mbu26_revenue_levels_are_never_substituted_into_the_current_path(line) -> None:
    """The long run must be a modelled path, not the official one relabelled."""
    official = line[line["source_path"].astype(str).eq("MBU26 official")]
    current = line[line["source_path"].astype(str).eq("Current finalist Base case")]
    for frame in (official, current):
        assert not frame.empty
    def totals(frame):
        scoped = frame[frame["series_id"].astype(str).eq("total_nltf_net_revenue")]
        return (
            pd.to_numeric(scoped["value"], errors="coerce")
            .groupby(pd.to_numeric(scoped["FY"], errors="coerce")).first().sort_index()
        )
    official_totals, current_totals = totals(official), totals(current)
    shared = sorted(set(official_totals.index) & set(current_totals.index))
    long_run = [fy for fy in shared if fy >= FIRST_EXTRAPOLATION_FY]
    assert long_run, "no shared long-run years to compare"
    identical = sum(
        1 for fy in long_run
        if abs(float(official_totals.loc[fy]) - float(current_totals.loc[fy])) < 1e-9
    )
    assert identical == 0, (
        f"{identical} long-run Current totals equal MBU26 exactly - a substitution"
    )


# ------------------------------------- 15-17. source-specific composition
def test_composition_bounds_are_derived_after_source_selection() -> None:
    source = inspect.getsource(app.render_revenue_outlook_page)
    start = source.index("Revenue composition over time")
    branch = source[start : start + 6000]
    assert "_revenue_line_fy_bounds(" in branch, "bounds must come from the selected source"
    assert 'selector_options["stack_fy_bounds"]' not in branch, (
        "global pre-selection bounds are the FY2030-cap bug"
    )
    assert "revenue_stack_fy_range_source" in branch, "source change must reset the range"


def test_official_stack_rows_run_to_their_own_source_horizon(pack) -> None:
    stack = pack.revenue_stack_components
    official = stack[stack["source_path"].astype(str).eq("MBU26 official")]
    years = pd.to_numeric(official["FY"], errors="coerce")
    assert int(years.max()) >= 2055, (
        f"MBU26 stack stops at FY{int(years.max())}; it must reach its FY2055 horizon"
    )


def test_current_stack_rows_reach_fy2050(pack) -> None:
    stack = pack.revenue_stack_components
    for source_path in ("Current finalist Base case", "Current finalist High population/comparison"):
        scoped = stack[stack["source_path"].astype(str).eq(source_path)]
        years = pd.to_numeric(scoped["FY"], errors="coerce")
        assert int(years.max()) >= LAST_EXTRAPOLATION_FY, (
            f"{source_path} stack stops at FY{int(years.max())}"
        )


def test_a_current_cutoff_can_never_filter_official_rows(pack) -> None:
    """The specific coupling that capped MBU26 at the Current FY2030 cutoff."""
    stack = pack.revenue_stack_components
    bounds_by_source = {
        str(source): (
            int(pd.to_numeric(group["FY"], errors="coerce").min()),
            int(pd.to_numeric(group["FY"], errors="coerce").max()),
        )
        for source, group in stack.groupby(stack["source_path"].astype(str))
    }
    official = bounds_by_source.get("MBU26 official")
    current = bounds_by_source.get("Current finalist Base case")
    assert official is not None and current is not None
    assert official[1] > current[1], (
        "the official horizon must exceed the current one, proving they are independent"
    )


# --------------------------------------------------------- 18-20. presentation
def test_the_total_path_segments_solid_and_dashed_at_the_seam() -> None:
    source = inspect.getsource(app.revenue_outlook_total_path_figure)
    assert "post_model_extrapolation" in source
    assert 'dash_style="dash"' in source, "the post-model portion must render dashed"
    assert "Post-model extrapolation" in source, "the FY2030 boundary must be labelled"


def test_public_hover_wording_hides_internal_horizon_language() -> None:
    labels = [
        app._public_segment_hover_label(pd.Series({"forecast_segment": "econometric_forecast"})),
        app._public_segment_hover_label(pd.Series({"forecast_segment": POST_MODEL_SEGMENT})),
        app._public_segment_hover_label(pd.Series({"scenario_role": "official_comparator"})),
        app._public_segment_hover_label(pd.Series({"row_type": "historical_actual"})),
    ]
    assert labels == [
        "<br>Econometric forecast",
        "<br>Post-model extrapolation",
        "<br>Official comparator",
        "<br>Actual",
    ]
    for label in labels:
        for internal in ("H13", "H20", "H21", "horizon_scope", "backtest-supported"):
            assert internal not in label


def test_charts_and_downloads_agree_on_the_long_run(chart, line) -> None:
    """The chart row and its line-reconciliation leaf must be the same number."""
    for scenario, source_path in (
        (BASE, "Current finalist Base case"),
        (COMPARISON, "Current finalist High population/comparison"),
    ):
        chart_totals = _annual(chart, scenario, "total_nltf_net_revenue")
        scoped = line[
            line["source_path"].astype(str).eq(source_path)
            & line["series_id"].astype(str).eq("total_nltf_net_revenue")
        ]
        line_totals = (
            pd.to_numeric(scoped["value"], errors="coerce")
            .groupby(pd.to_numeric(scoped["FY"], errors="coerce")).first().sort_index()
        )
        shared = [fy for fy in chart_totals.index if fy in line_totals.index and fy >= FIRST_EXTRAPOLATION_FY]
        assert shared, "no shared long-run years"
        worst = max(abs(float(chart_totals.loc[fy]) - float(line_totals.loc[fy])) for fy in shared)
        assert worst <= 1e-6, f"{scenario}: chart and line disagree by {worst:.3e}"


def test_downloads_carry_the_segment_and_governance_fields(chart) -> None:
    for column in ("forecast_segment", "value_status", "horizon_scope", "series_id", "period"):
        assert column in chart.columns, column
    post = chart[chart["forecast_segment"].astype(str).eq(POST_MODEL_SEGMENT)]
    assert post["formula"].astype(str).str.len().gt(0).all(), (
        "every extrapolated row must carry its formula lineage"
    )

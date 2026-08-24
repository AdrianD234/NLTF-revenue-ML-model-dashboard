"""The governed FY2031-FY2050 post-model extrapolation layer.

P0 withheld decision-facing Current values beyond H20/FY2030 because the
retired long-run construction was divergent: it divided a growing
conventional forecast by a conventional share approaching zero, implying a
Light RUC pool of ~185.8 billion km by FY2050 (~3.9x the VFM pool). That
withholding was a correct response to a broken constructor, not a statement
that no long-run view should exist.

This module is the replacement constructor. It is a separately named,
separately governed layer - ``forecast_segment = post_model_extrapolation`` -
that never touches the econometric FY2026-FY2030 path and is anchored on it:

PED         anchor FY2030 VKTpc x the committed raw AR(1) long-horizon path's
            own growth; light-petrol VKT keeps the production rule
            (VKTpc x scenario population) in growth space, so the implied
            population stays on the scenario path.
HEAVY RUC   anchor FY2030 km x the committed raw long-horizon path's growth.
            Heavy BEV keeps the fixed-component rule (carried from MBU26,
            exactly as FY2026-FY2030 does).
LIGHT RUC   a structural total-pool index, NOT share expansion:
                pool_fy = pool_2030 x (VFM_pool_fy / VFM_pool_2030)
            allocated with the exact vendored VFM shares. The index and the
            shares come from the same committed table
            (data/vfm_202405/vfm_vkt_shares.csv), which carries absolute
            per-class pools through 2050.
REVENUE     the same formula chain the FY2026-FY2030 bridge publishes on its
            rows: modelled activity x MBU26 effective rates, MBU26-carried
            fixed lines (LPG, CNG, refunds, admin, MVR, TUC, Heavy BEV),
            pure-sum aggregates. MBU26 revenue LEVELS are never substituted
            for a modelled stream.

Quarterly emission remains H1-H20. The raw audit layer remains
decision_facing=false. Everything here is annual, explicitly segmented, and
runs FY2031-FY2050 only.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .forecast_runner import repo_root_from_here
from .long_run_shape_transition import (
    FLEET_COMPOSITION_SOURCE_ID,
    LONG_RUN_SHAPE_METHOD_ID,
    UNBLENDED_SCHEDULE_ID,
    LongRunShapeTransitionError,
    TransitionSchedule,
    geometric_blend_index,
    growth_handover_index,
    resolve_schedule,
    structural_growth_indices,
    transition_weight,
)

__all__ = [
    "ECONOMETRIC_SEGMENT",
    "FIRST_EXTRAPOLATION_FY",
    "LAST_EXTRAPOLATION_FY",
    "POST_MODEL_SEGMENT",
    "POST_MODEL_VALUE_STATUS",
    "build_post_model_extrapolation_annual",
    "post_model_chart_rows",
    "post_model_line_reconciliation_rows",
    "stamp_forecast_segments",
    "anchor_index_level_audit",
    "anchor_shape_level_audit",
    "light_ruc_long_run_guard_frame",
    "light_fleet_composition_audit",
    "post_model_growth_indices",
]

ECONOMETRIC_SEGMENT = "econometric_forecast"
POST_MODEL_SEGMENT = "post_model_extrapolation"
POST_MODEL_VALUE_STATUS = "post_model_extrapolation"
FIRST_EXTRAPOLATION_FY = 2031
LAST_EXTRAPOLATION_FY = 2050
ANCHOR_FY = 2030

# The retired construction reached ~185,800 million km by FY2050. The guard
# refuses anything above twice the vendored VFM pool - generous headroom for
# a level anchor gap, far below the pathology.
LIGHT_POOL_MAX_RATIO_TO_VFM = 2.0
RETIRED_PATHOLOGY_FY2050_MILLION_KM = 185_800.0

# Growth guards. An anchored index is only a valid long-run forecast while it
# stays in economically plausible territory: a raw model path extrapolated 20
# years can compound a small drift into an absurd level, and the guards must
# catch that before anything reaches the dashboard rather than after.
MAX_ANNUAL_GROWTH_RATE = 0.15  # +15% in any single year
MIN_ANNUAL_GROWTH_RATE = -0.15
MAX_CUMULATIVE_INDEX = 4.0  # 4x the FY2030 anchor by FY2050
MIN_CUMULATIVE_INDEX = 0.25


def _guard_growth_index(
    values: pd.Series, *, label: str, scenario_name: str
) -> None:
    """Finite-value, year-on-year and cumulative guards on one index."""

    if not np.isfinite(values.to_numpy()).all():
        raise PostModelExtrapolationError(
            f"{scenario_name}: {label} index contains a non-finite value."
        )
    if (values <= 0.0).any():
        raise PostModelExtrapolationError(
            f"{scenario_name}: {label} index is non-positive; a level path cannot invert."
        )
    steps = values.sort_index().pct_change().dropna()
    if len(steps):
        worst_up = float(steps.max())
        worst_down = float(steps.min())
        if worst_up > MAX_ANNUAL_GROWTH_RATE:
            raise PostModelExtrapolationError(
                f"{scenario_name}: {label} grows {worst_up * 100:.1f}% in one year, "
                f"above the {MAX_ANNUAL_GROWTH_RATE * 100:.0f}% guard."
            )
        if worst_down < MIN_ANNUAL_GROWTH_RATE:
            raise PostModelExtrapolationError(
                f"{scenario_name}: {label} falls {worst_down * 100:.1f}% in one year, "
                f"below the {MIN_ANNUAL_GROWTH_RATE * 100:.0f}% guard."
            )
    terminal = float(values.sort_index().iloc[-1])
    if terminal > MAX_CUMULATIVE_INDEX or terminal < MIN_CUMULATIVE_INDEX:
        raise PostModelExtrapolationError(
            f"{scenario_name}: {label} terminal index {terminal:.3f} is outside "
            f"[{MIN_CUMULATIVE_INDEX}, {MAX_CUMULATIVE_INDEX}] - implausible long-run divergence."
        )

_VFM_SHARES_RELATIVE_PATH = Path("data") / "vfm_202405" / "vfm_vkt_shares.csv"
_VFM_DEFAULT_SCENARIO = "Base_EV"

# Line-reconciliation source_path labels per governed scenario.
_SOURCE_PATH_BY_SCENARIO = {
    "current_basecase": "Current finalist Base case",
    "current_comparison_1": "Current finalist High population/comparison",
}
_ROLE_BY_SCENARIO = {
    "current_basecase": "basecase",
    "current_comparison_1": "comparison",
}

# Lines carried from MBU26 by the FY2026-FY2030 bridge (their committed
# formula field is empty: they are official values, not modelled ones).
_OFFICIAL_CARRIED_SERIES = (
    "heavy_bev_ruc_net_km",
    "heavy_bev_ruc_net_revenue",
    "gross_lpg_revenue",
    "gross_cng_revenue",
    "fed_refunds",
    "ruc_admin_revenue",
    "ruc_refunds",
    "mr1_revenue",
    "mr2_revenue",
    "coo_revenue",
    "mvr_admin_revenue",
    "mvr_refunds",
    "tuc_net_revenue",
    "tuc_gtk",
)


class PostModelExtrapolationError(ValueError):
    """A governed input for the FY2031-FY2050 layer is missing or unusable."""


def _fy_of_quarter(period: str) -> int:
    year, quarter = int(str(period)[:4]), int(str(period)[5])
    return year + 1 if quarter >= 3 else year


def _numeric(series: pd.Series, context: str) -> pd.Series:
    out = pd.to_numeric(series, errors="coerce")
    if out.isna().any():
        raise PostModelExtrapolationError(f"{context}: non-numeric values present.")
    return out


def post_model_growth_indices(
    raw_quarterly_audit: pd.DataFrame,
    scenario_input_wide: pd.DataFrame,
    *,
    scenario_name: str,
    repo_root: Path | str | None = None,
    vfm_scenario: str = _VFM_DEFAULT_SCENARIO,
    long_run_shape_official_annual: pd.DataFrame | None = None,
    long_run_shape_vintage_id: str | None = None,
    transition_schedule_id: str = UNBLENDED_SCHEDULE_ID,
) -> pd.DataFrame:
    """Anchor-normalised growth indices for one governed scenario.

    Everything is committed input: the raw long-horizon audit path (the
    model's own H1-H100 output, decision_facing=false), the scenario's own
    population path, and the vendored VFM absolute pools. Every index equals
    exactly 1.0 at the FY2030 anchor by construction.

    When a long-run shape source is supplied, three further column families
    appear: ``s_*`` the structural growth indices taken from that vintage,
    ``w`` the governed transition weight, and ``h_*`` the geometric blend of
    the two. The ``h_*`` columns are what the constructor consumes; with the
    default ``unblended_current`` schedule they equal the Current indices
    exactly, so the merged-main behaviour is reproduced bit for bit.
    """

    root = Path(repo_root) if repo_root is not None else repo_root_from_here()
    schedule = resolve_schedule(transition_schedule_id)
    if schedule.is_structural and long_run_shape_official_annual is None:
        raise PostModelExtrapolationError(
            f"{scenario_name}: transition schedule {transition_schedule_id!r} needs a "
            "long-run shape source, but none was supplied. The extrapolation must "
            "fail closed rather than silently fall back to the unblended path."
        )
    scoped = raw_quarterly_audit[
        raw_quarterly_audit["scenario_name"].astype(str).eq(scenario_name)
    ].copy()
    if scoped.empty:
        raise PostModelExtrapolationError(
            f"raw long-horizon audit carries no rows for {scenario_name!r}; "
            "the extrapolation must fail closed rather than borrow another scenario."
        )
    scoped["fy"] = scoped["period"].astype(str).map(_fy_of_quarter)
    scoped["value"] = _numeric(scoped["value"], f"{scenario_name} raw audit values")

    population = scenario_input_wide[
        scenario_input_wide["scenario_name"].astype(str).eq(scenario_name)
        & scenario_input_wide["stream"].astype(str).eq("PED")
    ][["canonical_period", "population"]].copy()
    population["population"] = _numeric(
        population["population"], f"{scenario_name} population path"
    )

    ped = scoped[scoped["series_id"].astype(str).eq("ped_vkt_per_capita")].merge(
        population, left_on="period", right_on="canonical_period", how="left"
    )
    if ped["population"].isna().any():
        missing = sorted(ped.loc[ped["population"].isna(), "period"].astype(str))[:4]
        raise PostModelExtrapolationError(
            f"{scenario_name}: population is missing for raw PED quarters {missing}."
        )
    vktpc_fy = ped.groupby("fy")["value"].sum()
    petrol_fy = (ped["value"] * ped["population"]).groupby(ped["fy"]).sum()
    heavy_fy = (
        scoped[scoped["series_id"].astype(str).eq("heavy_ruc_net_km")]
        .groupby("fy")["value"]
        .sum()
    )

    vfm = pd.read_csv(root / _VFM_SHARES_RELATIVE_PATH)
    known_scenarios = sorted(vfm["scenario"].astype(str).unique())
    if str(vfm_scenario) not in known_scenarios:
        raise PostModelExtrapolationError(
            f"unknown VFM composition scenario {vfm_scenario!r}; "
            f"vendored scenarios: {known_scenarios}"
        )
    vfm = vfm[vfm["scenario"].astype(str).eq(str(vfm_scenario))].set_index("june_year")
    vfm_pool = (
        _numeric(vfm["light_ruc_conventional_million_km"], "VFM conventional pool")
        + _numeric(vfm["light_ruc_bev_million_km"], "VFM BEV pool")
        + _numeric(vfm["light_ruc_phev_million_km"], "VFM PHEV pool")
    )

    fys = list(range(ANCHOR_FY, LAST_EXTRAPOLATION_FY + 1))
    for name, series in (
        ("raw PED VKTpc", vktpc_fy),
        ("raw petrol VKT", petrol_fy),
        ("raw Heavy km", heavy_fy),
        ("VFM pool", vfm_pool),
    ):
        missing = [fy for fy in fys if fy not in series.index or not np.isfinite(series.loc[fy])]
        if missing:
            raise PostModelExtrapolationError(
                f"{scenario_name}: {name} does not cover {missing[:4]}; refusing to extrapolate."
            )
        if abs(series.loc[ANCHOR_FY]) <= 0.0:
            raise PostModelExtrapolationError(f"{scenario_name}: {name} anchor is zero.")

    frame = pd.DataFrame(
        {
            "fy": fys,
            "g_ped_vkt_per_capita": [vktpc_fy.loc[fy] / vktpc_fy.loc[ANCHOR_FY] for fy in fys],
            "g_light_petrol_vkt": [petrol_fy.loc[fy] / petrol_fy.loc[ANCHOR_FY] for fy in fys],
            "g_heavy_ruc_net_km": [heavy_fy.loc[fy] / heavy_fy.loc[ANCHOR_FY] for fy in fys],
            "vfm_pool_index": [vfm_pool.loc[fy] / vfm_pool.loc[ANCHOR_FY] for fy in fys],
            "vfm_conventional_share": [vfm.loc[fy, "light_ruc_conventional_share"] for fy in fys],
            "vfm_bev_share": [vfm.loc[fy, "light_ruc_bev_share"] for fy in fys],
            "vfm_phev_share": [vfm.loc[fy, "light_ruc_phev_share"] for fy in fys],
            "vfm_absolute_pool_million_km": [vfm_pool.loc[fy] for fy in fys],
            # The annual scenario population IMPLIED by the committed quarterly
            # path: petrol km divided by VKTpc is the VKT-weighted mean
            # population, and it is the only definition under which
            # `petrol = VKTpc x population` holds exactly at every FY - including
            # the FY2030 anchor. Deriving it here rather than averaging the four
            # quarters keeps the PED identity gate an equality rather than an
            # approximation, and leaves the population on the scenario's own path.
            "scenario_population": [petrol_fy.loc[fy] / vktpc_fy.loc[fy] for fy in fys],
        }
    )
    indexed = frame.set_index("fy")
    for column, label in (
        ("g_ped_vkt_per_capita", "PED VKT per capita"),
        ("g_light_petrol_vkt", "light petrol VKT"),
        ("g_heavy_ruc_net_km", "Heavy RUC km"),
        ("vfm_pool_index", "VFM Light RUC pool"),
    ):
        _guard_growth_index(indexed[column], label=label, scenario_name=scenario_name)
    frame["scenario_name"] = scenario_name
    share_sum = (
        frame["vfm_conventional_share"] + frame["vfm_bev_share"] + frame["vfm_phev_share"]
    )
    # The vendored table publishes shares at 6 dp, so raw sums deviate by up
    # to 1e-6. Anything beyond source precision is a real data problem;
    # within it, renormalise so class_sum == pool holds exactly.
    if (share_sum - 1.0).abs().max() > 2e-6:
        raise PostModelExtrapolationError(
            "VFM shares deviate from 1.0 beyond their published 6-dp precision."
        )
    for column in ("vfm_conventional_share", "vfm_bev_share", "vfm_phev_share"):
        frame[column] = frame[column] / share_sum

    return _attach_structural_transition(
        frame,
        scenario_name=scenario_name,
        schedule=schedule,
        long_run_shape_official_annual=long_run_shape_official_annual,
        long_run_shape_vintage_id=long_run_shape_vintage_id,
    )


def _attach_structural_transition(
    frame: pd.DataFrame,
    *,
    scenario_name: str,
    schedule: TransitionSchedule,
    long_run_shape_official_annual: pd.DataFrame | None,
    long_run_shape_vintage_id: str | None,
) -> pd.DataFrame:
    """Add the structural index, the transition weight and the blend.

    The Current index for each stream is the one the merged extrapolator
    already used, so ``unblended_current`` reproduces merged main exactly:

    PED        the raw long-horizon petrol VKT growth
    LIGHT RUC  the vendored VFM absolute pool index (the existing structural
               total-pool index, which IS the unblended Current pool path)
    HEAVY RUC  the raw long-horizon Heavy RUC growth

    Only the three POOL/level indices are blended. Class composition stays with
    the exact VFM shares, and PED VKTpc is derived from blended petrol VKT and
    the scenario population rather than blended on its own - so the activity
    identities cannot drift apart.
    """

    out = frame.copy()
    out["transition_schedule_id"] = schedule.schedule_id
    out["transition_anchor_fy"] = schedule.anchor_fy
    out["transition_completion_fy"] = (
        schedule.completion_fy if schedule.is_structural else pd.NA
    )
    out["w"] = np.asarray(
        transition_weight(
            out["fy"].to_numpy(),
            anchor_fy=schedule.anchor_fy,
            completion_fy=schedule.completion_fy,
        ),
        dtype=float,
    )

    current_columns = {
        "light_petrol_vkt": "g_light_petrol_vkt",
        "light_ruc_pool": "vfm_pool_index",
        "heavy_ruc_net_km": "g_heavy_ruc_net_km",
    }

    if long_run_shape_official_annual is None:
        out["long_run_shape_vintage_id"] = ""
        for stream, current_column in current_columns.items():
            out[f"s_{stream}"] = np.nan
            out[f"h_{stream}"] = out[current_column].to_numpy(dtype=float)
        return out

    vintage_id = str(long_run_shape_vintage_id or "unnamed_shape_vintage")
    try:
        structural = structural_growth_indices(
            long_run_shape_official_annual,
            vintage_id=vintage_id,
            first_fy=ANCHOR_FY,
            last_fy=LAST_EXTRAPOLATION_FY,
        ).set_index("fy")
    except LongRunShapeTransitionError as error:
        raise PostModelExtrapolationError(
            f"{scenario_name}: long-run shape source {vintage_id} is unusable: {error}"
        ) from error

    out["long_run_shape_vintage_id"] = vintage_id
    for stream, current_column in current_columns.items():
        structural_index = structural.loc[out["fy"].to_numpy(), f"s_{stream}"].to_numpy(
            dtype=float
        )
        current_index = out[current_column].to_numpy(dtype=float)
        out[f"s_{stream}"] = structural_index
        out[f"s_level_{stream}"] = structural.loc[
            out["fy"].to_numpy(), f"s_level_{stream}"
        ].to_numpy(dtype=float)
        try:
            if schedule.is_growth_handover:
                out[f"h_{stream}"] = growth_handover_index(
                    current_index,
                    structural_index,
                    out["w"].to_numpy(dtype=float),
                    context=f"{scenario_name} {stream}",
                )
            else:
                out[f"h_{stream}"] = geometric_blend_index(
                    current_index,
                    structural_index,
                    out["w"].to_numpy(dtype=float),
                    context=f"{scenario_name} {stream}",
                )
        except LongRunShapeTransitionError as error:
            raise PostModelExtrapolationError(str(error)) from error
        _guard_growth_index(
            out.set_index("fy")[f"h_{stream}"],
            label=f"hybrid {stream}",
            scenario_name=scenario_name,
        )
    return out


def _current_anchors(
    line_reconciliation: pd.DataFrame, scenario_name: str
) -> dict[str, float]:
    source_path = _SOURCE_PATH_BY_SCENARIO.get(scenario_name)
    if source_path is None:
        raise PostModelExtrapolationError(f"No governed source path for {scenario_name!r}.")
    scoped = line_reconciliation[
        line_reconciliation["source_path"].astype(str).eq(source_path)
        & pd.to_numeric(line_reconciliation["FY"], errors="coerce").eq(ANCHOR_FY)
    ]
    anchors: dict[str, float] = {}
    for row in scoped.itertuples():
        value = pd.to_numeric(pd.Series([row.value]), errors="coerce").iloc[0]
        if pd.notna(value):
            anchors[str(row.series_id)] = float(value)
    required = (
        "ped_vkt_per_capita",
        "light_petrol_vkt",
        "heavy_ruc_net_km",
        "light_ruc_net_km",
        "light_bev_ruc_net_km",
        "phev_ruc_net_km",
    )
    missing = [series for series in required if series not in anchors]
    if missing:
        raise PostModelExtrapolationError(
            f"{scenario_name}: FY{ANCHOR_FY} anchors missing for {missing}."
        )
    return anchors


def _official_lookup(mbu26_official_annual: pd.DataFrame) -> pd.DataFrame:
    wide = mbu26_official_annual.pivot_table(
        index="FY", columns="series_id", values="value", aggfunc="first"
    )
    fys = range(FIRST_EXTRAPOLATION_FY, LAST_EXTRAPOLATION_FY + 1)
    needed = [
        "light_ruc_net_km", "light_ruc_net_revenue",
        "light_bev_ruc_net_km", "light_bev_ruc_net_revenue",
        "phev_ruc_net_km", "phev_ruc_net_revenue",
        "heavy_ruc_net_km", "heavy_ruc_net_revenue",
        "light_petrol_vkt", "ped_volume", "gross_ped_revenue",
        *_OFFICIAL_CARRIED_SERIES,
    ]
    for fy in fys:
        if fy not in wide.index:
            raise PostModelExtrapolationError(f"MBU26 official spine is missing FY{fy}.")
        for series in needed:
            if series not in wide.columns or pd.isna(wide.at[fy, series]):
                raise PostModelExtrapolationError(
                    f"MBU26 official spine is missing {series!r} at FY{fy}."
                )
    return wide


def build_post_model_extrapolation_annual(
    *,
    line_reconciliation: pd.DataFrame,
    raw_quarterly_audit: pd.DataFrame,
    scenario_input_wide: pd.DataFrame,
    mbu26_official_annual: pd.DataFrame,
    scenario_names: tuple[str, ...] = ("current_basecase", "current_comparison_1"),
    repo_root: Path | str | None = None,
    vfm_scenario: str = _VFM_DEFAULT_SCENARIO,
    long_run_shape_official_annual: pd.DataFrame | None = None,
    long_run_shape_vintage_id: str | None = None,
    transition_schedule_id: str = UNBLENDED_SCHEDULE_ID,
) -> pd.DataFrame:
    """Every FY2031-FY2050 leaf and aggregate for every governed scenario.

    Returns a long frame keyed (scenario_name, fy, series_id) with value,
    unit, formula and segment columns. Aggregates are built from the leaves
    in this frame, so closure is by construction and separately re-checked by
    the caller's gates.

    ``mbu26_official_annual`` is the BRIDGE-assumption vintage: effective
    rates, fuel intensity and the carried fixed lines. ``long_run_shape_*`` is
    the separately governed SHAPE vintage, used only for growth indices. The
    two are independent by construction - the shape source supplies no level,
    no rate and no fixed line, and the bridge source supplies no growth index.
    """

    official = _official_lookup(mbu26_official_annual)
    schedule = resolve_schedule(transition_schedule_id)
    rows: list[dict[str, object]] = []

    def emit(scenario: str, fy: int, series: str, value: float, unit: str, formula: str) -> None:
        rows.append(
            {
                "scenario_name": scenario,
                "scenario_role": _ROLE_BY_SCENARIO[scenario],
                "source_path": _SOURCE_PATH_BY_SCENARIO[scenario],
                "fy": fy,
                "series_id": series,
                "value": float(value),
                "unit": unit,
                "formula": formula,
                "forecast_segment": POST_MODEL_SEGMENT,
                "value_status": POST_MODEL_VALUE_STATUS,
                "decision_facing": True,
                "long_run_shape_method_id": LONG_RUN_SHAPE_METHOD_ID,
                "long_run_transition_schedule_id": schedule.schedule_id,
                "long_run_shape_vintage_id": str(long_run_shape_vintage_id or ""),
                "fleet_composition_source_id": FLEET_COMPOSITION_SOURCE_ID,
                "fleet_composition_scenario": str(vfm_scenario),
            }
        )

    # Provenance strings name the actual construction, so a reader of the line
    # table can tell an unblended row from a transitioned one without consulting
    # the manifest.
    if schedule.is_structural:
        shape_token = str(long_run_shape_vintage_id or "long-run shape vintage")
        if schedule.is_growth_handover:
            blend = (
                f"with the growth rate handed over one-way to the {shape_token} "
                f"growth shape ({schedule.schedule_id}, complete FY{schedule.completion_fy})"
            )
        else:
            blend = (
                f"geometrically blended toward the {shape_token} growth shape "
                f"({schedule.schedule_id}, complete FY{schedule.completion_fy})"
            )
        petrol_formula = f"FY{ANCHOR_FY} petrol anchor * Current growth {blend}"
        heavy_formula = f"FY{ANCHOR_FY} Heavy anchor * Current growth {blend}"
        pool_formula = f"FY{ANCHOR_FY} pool anchor * VFM pool index {blend}"
    else:
        petrol_formula = (
            f"FY{ANCHOR_FY} petrol anchor * raw (VKTpc x scenario population) growth"
        )
        heavy_formula = f"FY{ANCHOR_FY} Heavy anchor * raw long-horizon growth"
        pool_formula = f"structural pool (FY{ANCHOR_FY} anchor * VFM pool index)"

    for scenario in scenario_names:
        anchors = _current_anchors(line_reconciliation, scenario)
        growth = post_model_growth_indices(
            raw_quarterly_audit,
            scenario_input_wide,
            scenario_name=scenario,
            repo_root=repo_root,
            vfm_scenario=vfm_scenario,
            long_run_shape_official_annual=long_run_shape_official_annual,
            long_run_shape_vintage_id=long_run_shape_vintage_id,
            transition_schedule_id=transition_schedule_id,
        ).set_index("fy")
        pool_anchor = (
            anchors["light_ruc_net_km"]
            + anchors["light_bev_ruc_net_km"]
            + anchors["phev_ruc_net_km"]
        )
        for fy in range(FIRST_EXTRAPOLATION_FY, LAST_EXTRAPOLATION_FY + 1):
            g = growth.loc[fy]

            # ---------------- activity
            # Every stream is its own FY2030 Current anchor times a HYBRID
            # growth index. With the unblended schedule the hybrid index is the
            # Current index, so these are the merged-main values exactly.
            petrol = anchors["light_petrol_vkt"] * g["h_light_petrol_vkt"]
            heavy = anchors["heavy_ruc_net_km"] * g["h_heavy_ruc_net_km"]
            pool = pool_anchor * g["h_light_ruc_pool"]
            # VKTpc is DERIVED from blended petrol VKT and the scenario's own
            # population rather than blended separately, so
            # `petrol = VKTpc x population` holds exactly instead of the two
            # drifting apart under the blend. No official population is ever
            # inferred: the population is the Current scenario path's own.
            vktpc = petrol * 1_000_000.0 / g["scenario_population"]
            # Composition stays with the exact vendored VFM shares. The blend
            # moves the POOL only; it never touches the class split.
            conventional = pool * g["vfm_conventional_share"]
            bev = pool * g["vfm_bev_share"]
            phev = pool * g["vfm_phev_share"]
            if pool > LIGHT_POOL_MAX_RATIO_TO_VFM * g["vfm_absolute_pool_million_km"]:
                raise PostModelExtrapolationError(
                    f"{scenario} FY{fy}: Light pool {pool:.0f} Mkm exceeds "
                    f"{LIGHT_POOL_MAX_RATIO_TO_VFM}x the VFM pool - the divergence "
                    "guard that retired the previous constructor."
                )
            # litres intensity and effective rates from the official spine.
            intensity = official.at[fy, "ped_volume"] * 100.0 / official.at[fy, "light_petrol_vkt"]
            ped_volume = petrol * intensity / 100.0

            emit(scenario, fy, "ped_vkt_per_capita", vktpc, "km/person",
                 f"{petrol_formula} / scenario population")
            emit(scenario, fy, "light_petrol_vkt", petrol, "million km", petrol_formula)
            emit(scenario, fy, "ped_volume", ped_volume, "million litres",
                 "extrapolated petrol VKT * bridge-vintage litres intensity / 100")
            emit(scenario, fy, "heavy_ruc_net_km", heavy, "million km", heavy_formula)
            emit(scenario, fy, "light_ruc_net_km", conventional, "million km",
                 f"{pool_formula} * exact VFM conventional share")
            emit(scenario, fy, "light_bev_ruc_net_km", bev, "million km",
                 f"{pool_formula} * exact VFM Light BEV share")
            emit(scenario, fy, "phev_ruc_net_km", phev, "million km",
                 f"{pool_formula} * exact VFM PHEV share")
            emit(scenario, fy, "current_light_ruc_conventional_modelled_km", conventional,
                 "million km", "conventional class of the structural pool")

            # ---------------- revenue: modelled activity x MBU26 effective rates
            def rate(revenue_series: str, activity_series: str) -> float:
                activity = float(official.at[fy, activity_series])
                if abs(activity) <= 0.0:
                    raise PostModelExtrapolationError(
                        f"MBU26 {activity_series} is zero at FY{fy}; no effective rate."
                    )
                return float(official.at[fy, revenue_series]) / activity

            light_rev = conventional * rate("light_ruc_net_revenue", "light_ruc_net_km")
            bev_rev = bev * rate("light_bev_ruc_net_revenue", "light_bev_ruc_net_km")
            phev_rev = phev * rate("phev_ruc_net_revenue", "phev_ruc_net_km")
            heavy_rev = heavy * rate("heavy_ruc_net_revenue", "heavy_ruc_net_km")
            gross_ped = ped_volume * (
                float(official.at[fy, "gross_ped_revenue"]) / float(official.at[fy, "ped_volume"])
            )
            emit(scenario, fy, "light_ruc_net_revenue", light_rev, "$m nominal ex GST",
                 "conventional Light RUC km * MBU26 conventional Light effective rate")
            emit(scenario, fy, "light_bev_ruc_net_revenue", bev_rev, "$m nominal ex GST",
                 "allocated Light BEV RUC km * MBU26 Light BEV effective rate")
            emit(scenario, fy, "phev_ruc_net_revenue", phev_rev, "$m nominal ex GST",
                 "allocated PHEV RUC km * MBU26 PHEV effective rate")
            emit(scenario, fy, "heavy_ruc_net_revenue", heavy_rev, "$m nominal ex GST",
                 "extrapolated Heavy RUC km * MBU26 effective rate")
            emit(scenario, fy, "gross_ped_revenue", gross_ped, "$m nominal ex GST",
                 "extrapolated PED litres * MBU26 PED rate")

            # ---------------- MBU26-carried fixed lines (same rule as FY2026-30)
            carried: dict[str, float] = {}
            for series in _OFFICIAL_CARRIED_SERIES:
                value = float(official.at[fy, series])
                carried[series] = value
                unit = "million km" if series.endswith("_km") else (
                    "million tonne-km" if series == "tuc_gtk" else "$m nominal ex GST"
                )
                emit(scenario, fy, series, value, unit, "carried from MBU26 official (fixed line)")

            # ---------------- aggregates (the committed formula chain)
            # The governed expression is gross RUC INCLUSIVE of refunds:
            #   gross_ruc = light + heavy + light BEV + heavy BEV + PHEV + ruc_refunds
            # and total_ruc_net_revenue subtracts them again downstream. An
            # earlier revision omitted the refunds term, so gross RUC and every
            # aggregate above it failed the governed residual check by ~$118m
            # at FY2031. Mirror the committed formula exactly rather than a
            # plausible reconstruction of it.
            gross_ruc = (
                light_rev
                + heavy_rev
                + bev_rev
                + carried["heavy_bev_ruc_net_revenue"]
                + phev_rev
                + carried["ruc_refunds"]
            )
            ruc_net_admin = gross_ruc - carried["ruc_admin_revenue"]
            total_ruc = ruc_net_admin - carried["ruc_refunds"]
            gross_fed = gross_ped + carried["gross_lpg_revenue"] + carried["gross_cng_revenue"]
            net_fed = gross_fed - carried["fed_refunds"]
            gross_mvr = carried["mr1_revenue"] + carried["mr2_revenue"] + carried["coo_revenue"]
            mvr_net_admin_coo = carried["mr1_revenue"] + carried["mr2_revenue"] - carried["mvr_admin_revenue"]
            net_mvr = mvr_net_admin_coo - carried["mvr_refunds"]
            total_gross = gross_ruc + gross_fed + gross_mvr + carried["tuc_net_revenue"]
            total_admin = carried["ruc_admin_revenue"] + carried["mvr_admin_revenue"] + carried["coo_revenue"]
            total_net_admin = total_gross - total_admin
            total_refunds = carried["ruc_refunds"] + carried["fed_refunds"] + carried["mvr_refunds"]
            total_nltf = total_net_admin - total_refunds
            for series, value, formula in (
                ("gross_ruc_revenue", gross_ruc,
                 "light + heavy + light BEV + MBU26 heavy BEV + PHEV RUC revenue + MBU26 ruc_refunds"),
                ("ruc_revenue_net_admin", ruc_net_admin, "gross_ruc_revenue - MBU26 ruc_admin_revenue"),
                ("total_ruc_net_revenue", total_ruc, "ruc_revenue_net_admin - MBU26 ruc_refunds"),
                ("gross_fed_revenue", gross_fed, "gross_ped_revenue + MBU26 LPG + MBU26 CNG"),
                ("net_fed_revenue", net_fed, "gross_fed_revenue - MBU26 fed_refunds"),
                ("gross_mvr_revenue", gross_mvr, "MR1 + MR2 + COO"),
                ("mvr_revenue_net_admin_coo", mvr_net_admin_coo, "MR1 + MR2 - mvr_admin_revenue"),
                ("net_mvr_revenue", net_mvr, "mvr_revenue_net_admin_coo - mvr_refunds"),
                ("total_gross_revenue", total_gross, "gross RUC + gross FED + gross MVR + TUC"),
                ("total_admin_fees", total_admin, "ruc_admin + mvr_admin + coo"),
                ("total_revenue_net_admin", total_net_admin, "total_gross_revenue - total_admin_fees"),
                ("total_refunds", total_refunds, "ruc + fed + mvr refunds"),
                ("total_nltf_net_revenue", total_nltf, "total_revenue_net_admin - total_refunds"),
                ("total_fed_ruc_net_revenue", net_fed + total_ruc, "net_fed_revenue + total_ruc_net_revenue"),
            ):
                emit(scenario, fy, series, value, "$m nominal ex GST", formula)

    return pd.DataFrame(rows)


def anchor_shape_level_audit(
    *,
    line_reconciliation: pd.DataFrame,
    raw_quarterly_audit: pd.DataFrame,
    scenario_input_wide: pd.DataFrame,
    long_run_shape_official_annual: pd.DataFrame,
    long_run_shape_vintage_id: str,
    transition_schedule_id: str,
    scenario_names: tuple[str, ...] = ("current_basecase", "current_comparison_1"),
    repo_root: Path | str | None = None,
    vfm_scenario: str = _VFM_DEFAULT_SCENARIO,
) -> pd.DataFrame:
    """Anchor, Current index, structural index, weight, blend and level.

    One row per (scenario, stream, FY) showing every term of the transition
    separately, so a reviewer can confirm by arithmetic that the level is the
    FY2030 Current anchor times a blend of two indices - and that no official
    LEVEL was substituted. The official level is carried alongside precisely so
    the ratio to it is visible rather than implied.
    """

    schedule = resolve_schedule(transition_schedule_id)
    streams = (
        ("light_petrol_vkt", "light_petrol_vkt", "g_light_petrol_vkt"),
        ("light_ruc_total_pool", "light_ruc_pool", "vfm_pool_index"),
        ("heavy_ruc_net_km", "heavy_ruc_net_km", "g_heavy_ruc_net_km"),
    )
    rows: list[dict[str, object]] = []
    for scenario in scenario_names:
        anchors = _current_anchors(line_reconciliation, scenario)
        growth = post_model_growth_indices(
            raw_quarterly_audit,
            scenario_input_wide,
            scenario_name=scenario,
            repo_root=repo_root,
            vfm_scenario=vfm_scenario,
            long_run_shape_official_annual=long_run_shape_official_annual,
            long_run_shape_vintage_id=long_run_shape_vintage_id,
            transition_schedule_id=transition_schedule_id,
        ).set_index("fy")
        anchor_by_stream = {
            "light_petrol_vkt": anchors["light_petrol_vkt"],
            "light_ruc_total_pool": (
                anchors["light_ruc_net_km"]
                + anchors["light_bev_ruc_net_km"]
                + anchors["phev_ruc_net_km"]
            ),
            "heavy_ruc_net_km": anchors["heavy_ruc_net_km"],
        }
        # Recompute each hybrid index independently of the constructor so the
        # audit is a check, not a restatement. The level blend is a per-year
        # closed form; the growth handover integrates its recurrence from the
        # anchor, so it is recomputed as a series per stream up front.
        recomputed_by_stream: dict[str, pd.Series] = {}
        if schedule.is_growth_handover:
            ordered_fys = sorted(growth.index)
            for _, stream, current_column in streams:
                current_series = growth.loc[ordered_fys, current_column].to_numpy(dtype=float)
                structural_series = growth.loc[ordered_fys, f"s_{stream}"].to_numpy(dtype=float)
                weight_series = growth.loc[ordered_fys, "w"].to_numpy(dtype=float)
                recomputed = np.ones(len(ordered_fys), dtype=float)
                for position in range(1, len(ordered_fys)):
                    step_weight = weight_series[position]
                    recomputed[position] = recomputed[position - 1] * (
                        (current_series[position] / current_series[position - 1])
                        ** (1.0 - step_weight)
                        * (structural_series[position] / structural_series[position - 1])
                        ** step_weight
                    )
                recomputed_by_stream[stream] = pd.Series(recomputed, index=ordered_fys)
        for fy in range(FIRST_EXTRAPOLATION_FY, LAST_EXTRAPOLATION_FY + 1):
            row = growth.loc[fy]
            for label, stream, current_column in streams:
                anchor = float(anchor_by_stream[label])
                current_index = float(row[current_column])
                structural_index = float(row[f"s_{stream}"])
                weight = float(row["w"])
                hybrid_index = float(row[f"h_{stream}"])
                official_level = float(row.get(f"s_level_{stream}", np.nan))
                official_anchor_level = float(
                    growth.at[ANCHOR_FY, f"s_level_{stream}"]
                    if f"s_level_{stream}" in growth.columns
                    else np.nan
                )
                hybrid_level = anchor * hybrid_index
                rows.append(
                    {
                        "scenario_name": scenario,
                        "fy": fy,
                        "series_id": label,
                        "transition_schedule_id": schedule.schedule_id,
                        "long_run_shape_vintage_id": long_run_shape_vintage_id,
                        "anchor_fy": ANCHOR_FY,
                        "current_fy2030_anchor_level": anchor,
                        "current_growth_index": current_index,
                        "structural_growth_index": structural_index,
                        "transition_weight_w": weight,
                        "model_weight": 1.0 - weight,
                        "hybrid_growth_index": hybrid_index,
                        "hybrid_level": hybrid_level,
                        "recomputed_hybrid_index": (
                            float(recomputed_by_stream[stream].loc[fy])
                            if schedule.is_growth_handover
                            else current_index ** (1.0 - weight) * structural_index**weight
                        ),
                        "official_level_same_fy": official_level,
                        "official_level_anchor_fy": official_anchor_level,
                        "hybrid_over_official_ratio": (
                            hybrid_level / official_level
                            if np.isfinite(official_level) and official_level != 0.0
                            else np.nan
                        ),
                        "anchor_over_official_anchor_ratio": (
                            anchor / official_anchor_level
                            if np.isfinite(official_anchor_level)
                            and official_anchor_level != 0.0
                            else np.nan
                        ),
                        "official_level_substituted": False,
                        "construction": (
                            "current_fy2030_anchor x cumulative "
                            "((c_t/c_{t-1})**(1-w_t) * (s_t/s_{t-1})**w_t) from the anchor"
                            if schedule.is_growth_handover
                            else "current_fy2030_anchor x "
                            "(current_index**(1-w) * structural_index**w)"
                        ),
                    }
                )
    frame = pd.DataFrame(rows)
    drift = (frame["hybrid_growth_index"] - frame["recomputed_hybrid_index"]).abs()
    if float(drift.max()) > 1e-12:
        raise PostModelExtrapolationError(
            f"anchor/shape audit does not reproduce the constructor's blend "
            f"(worst {float(drift.max()):.3e})."
        )
    return frame


def anchor_index_level_audit(
    *,
    line_reconciliation: pd.DataFrame,
    raw_quarterly_audit: pd.DataFrame,
    scenario_input_wide: pd.DataFrame,
    scenario_names: tuple[str, ...] = ("current_basecase", "current_comparison_1"),
    repo_root: Path | str | None = None,
) -> pd.DataFrame:
    """Anchor, index and resulting level reported SEPARATELY per cell.

    The point is auditability: a reader can confirm the raw model path was
    used as a growth index against the corrected FY2030 anchor, and was never
    republished at its own level. ``raw_level`` is the raw path's own value -
    shown precisely so the divergence between it and ``extrapolated_level``
    is visible rather than implied.
    """

    rows: list[dict[str, object]] = []
    for scenario in scenario_names:
        anchors = _current_anchors(line_reconciliation, scenario)
        growth = post_model_growth_indices(
            raw_quarterly_audit, scenario_input_wide,
            scenario_name=scenario, repo_root=repo_root,
        ).set_index("fy")
        raw = raw_quarterly_audit[
            raw_quarterly_audit["scenario_name"].astype(str).eq(scenario)
        ].copy()
        raw["fy"] = raw["period"].astype(str).map(_fy_of_quarter)
        raw["value"] = pd.to_numeric(raw["value"], errors="coerce")
        raw_annual = raw.groupby(["series_id", "fy"])["value"].sum()
        pool_anchor = (
            anchors["light_ruc_net_km"]
            + anchors["light_bev_ruc_net_km"]
            + anchors["phev_ruc_net_km"]
        )
        specs = (
            ("ped_vkt_per_capita", anchors["ped_vkt_per_capita"], "g_ped_vkt_per_capita",
             "raw AR(1) long-horizon VKTpc path"),
            ("light_petrol_vkt", anchors["light_petrol_vkt"], "g_light_petrol_vkt",
             "raw VKTpc x scenario population"),
            ("heavy_ruc_net_km", anchors["heavy_ruc_net_km"], "g_heavy_ruc_net_km",
             "raw Heavy RUC long-horizon path"),
            ("light_ruc_total_pool", pool_anchor, "vfm_pool_index",
             "vendored VFM Base absolute total pool"),
        )
        for fy in range(FIRST_EXTRAPOLATION_FY, LAST_EXTRAPOLATION_FY + 1):
            for series, anchor_value, index_column, basis in specs:
                index_value = float(growth.at[fy, index_column])
                raw_level = raw_annual.get((series, fy), np.nan)
                rows.append(
                    {
                        "scenario_name": scenario,
                        "fy": fy,
                        "series_id": series,
                        "anchor_fy": ANCHOR_FY,
                        "corrected_anchor_level": float(anchor_value),
                        "growth_index": index_value,
                        "index_basis": basis,
                        "extrapolated_level": float(anchor_value) * index_value,
                        "raw_path_own_level": float(raw_level) if pd.notna(raw_level) else np.nan,
                        "raw_path_own_level_note": (
                            "raw audit native units (km for the RUC streams, so a "
                            "1e6 offset from the million-km extrapolated level); "
                            "shown to prove the raw LEVEL was not republished"
                        ),
                        "republished_raw_level": False,
                        "construction": "corrected_anchor x growth_index",
                    }
                )
    return pd.DataFrame(rows)


def light_fleet_composition_audit(
    *,
    hybrid_pool_by_fy: dict[int, float],
    repo_root: Path | str | None = None,
    official_shares: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Allocate one hybrid pool under every composition source, side by side.

    The exact VFM Base/Fast/Slow shares are the PRODUCTION source. Official
    embedded shares are carried here as audit comparisons only - they are never
    the Current default, and PR #11's composition-refresh candidate stays an
    opt-in owner decision.

    Fast and Slow change the class SPLIT of a given pool; they never change the
    pool total. That is asserted by the caller's gates and is visible here
    because every row shares the same ``hybrid_pool_million_km``.
    """

    root = Path(repo_root) if repo_root is not None else repo_root_from_here()
    vfm = pd.read_csv(root / _VFM_SHARES_RELATIVE_PATH)
    rows: list[dict[str, object]] = []

    for scenario in sorted(vfm["scenario"].astype(str).unique()):
        scoped = vfm[vfm["scenario"].astype(str).eq(scenario)].set_index("june_year")
        for fy, pool in sorted(hybrid_pool_by_fy.items()):
            if fy not in scoped.index:
                continue
            shares = {
                "conventional": float(scoped.at[fy, "light_ruc_conventional_share"]),
                "bev": float(scoped.at[fy, "light_ruc_bev_share"]),
                "phev": float(scoped.at[fy, "light_ruc_phev_share"]),
            }
            total = sum(shares.values())
            rows.append(
                {
                    "composition_source": f"exact_VFM_{scenario}",
                    "composition_role": (
                        "production_default"
                        if scenario == _VFM_DEFAULT_SCENARIO
                        else "governed_alternative"
                    ),
                    "fy": fy,
                    "hybrid_pool_million_km": float(pool),
                    "conventional_share": shares["conventional"] / total,
                    "bev_share": shares["bev"] / total,
                    "phev_share": shares["phev"] / total,
                    "conventional_million_km": pool * shares["conventional"] / total,
                    "light_bev_million_km": pool * shares["bev"] / total,
                    "phev_million_km": pool * shares["phev"] / total,
                    "raw_share_sum": total,
                }
            )

    for vintage_id, official_annual in (official_shares or {}).items():
        wide = official_annual.pivot_table(
            index="FY", columns="series_id", values="value", aggfunc="first"
        )
        for fy, pool in sorted(hybrid_pool_by_fy.items()):
            if fy not in wide.index:
                continue
            classes = {
                "conventional": float(wide.at[fy, "light_ruc_net_km"]),
                "bev": float(wide.at[fy, "light_bev_ruc_net_km"]),
                "phev": float(wide.at[fy, "phev_ruc_net_km"]),
            }
            total = sum(classes.values())
            if total <= 0.0:
                continue
            rows.append(
                {
                    "composition_source": f"{vintage_id}_embedded_shares",
                    "composition_role": "audit_only",
                    "fy": fy,
                    "hybrid_pool_million_km": float(pool),
                    "conventional_share": classes["conventional"] / total,
                    "bev_share": classes["bev"] / total,
                    "phev_share": classes["phev"] / total,
                    "conventional_million_km": pool * classes["conventional"] / total,
                    "light_bev_million_km": pool * classes["bev"] / total,
                    "phev_million_km": pool * classes["phev"] / total,
                    "raw_share_sum": 1.0,
                }
            )

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    classes_sum = (
        frame["conventional_million_km"]
        + frame["light_bev_million_km"]
        + frame["phev_million_km"]
    )
    frame["class_sum_million_km"] = classes_sum
    frame["class_sum_minus_pool"] = classes_sum - frame["hybrid_pool_million_km"]
    worst = float(frame["class_sum_minus_pool"].abs().max())
    tolerance = 1e-9 * max(1.0, float(frame["hybrid_pool_million_km"].abs().max()))
    if worst > tolerance:
        raise PostModelExtrapolationError(
            f"light fleet composition audit: classes do not sum to the pool "
            f"(worst {worst:.3e} > {tolerance:.3e})."
        )
    return frame


def light_ruc_long_run_guard_frame(extrapolation: pd.DataFrame) -> pd.DataFrame:
    """The committed divergence evidence: pool, ratio to VFM, and the ban."""

    pools = extrapolation[
        extrapolation["series_id"].isin(
            ["light_ruc_net_km", "light_bev_ruc_net_km", "phev_ruc_net_km"]
        )
    ]
    grouped = pools.groupby(["scenario_name", "fy"])["value"].sum().rename("pool_million_km")
    frame = grouped.reset_index()
    frame["retired_pathology_million_km"] = 185_800.0
    frame["pool_vs_pathology_ratio"] = frame["pool_million_km"] / 185_800.0
    return frame


def post_model_line_reconciliation_rows(
    line_reconciliation: pd.DataFrame,
    extrapolation: pd.DataFrame,
) -> pd.DataFrame:
    """Map the extrapolation frame into line-reconciliation-schema rows.

    Each (source_path, series) clones its FY2030 row as the metadata template
    - section, labels, units, fed_path all stay convention-identical - and
    overrides the period, value, status and lineage fields. Quarter
    composition is blanked: the post-model layer is annual-only by
    construction and must never imply quarters exist.
    """

    if extrapolation is None or extrapolation.empty:
        return pd.DataFrame(columns=line_reconciliation.columns)
    templates: dict[tuple[str, str], pd.Series] = {}
    anchor_rows = line_reconciliation[
        pd.to_numeric(line_reconciliation["FY"], errors="coerce").eq(ANCHOR_FY)
    ]
    for row in anchor_rows.itertuples(index=True):
        templates[(str(row.source_path), str(row.series_id))] = anchor_rows.loc[row.Index]

    # The line table's own inventory at the anchor year defines which series
    # belong in it. Chart-only aggregates (total_fed_ruc_net_revenue) are
    # legitimately absent here and live in the chart rows instead; a series
    # the line table DOES carry but a scenario lacks is a genuine failure.
    line_series_by_path: dict[str, set[str]] = {}
    for source_path, series_id in templates:
        line_series_by_path.setdefault(source_path, set()).add(series_id)

    out_rows: list[pd.Series] = []
    missing_templates: set[tuple[str, str]] = set()
    for record in extrapolation.itertuples():
        key = (str(record.source_path), str(record.series_id))
        template = templates.get(key)
        if template is None:
            if str(record.series_id) in line_series_by_path.get(str(record.source_path), set()):
                missing_templates.add(key)
            continue
        cloned = template.copy()
        cloned["FY"] = int(record.fy)
        cloned["period"] = f"FY{int(record.fy)}"
        cloned["value"] = float(record.value)
        cloned["formula"] = str(record.formula)
        cloned["value_status"] = POST_MODEL_VALUE_STATUS
        cloned["source_basis"] = "post_model_structural_extrapolation"
        cloned["source_file"] = "post_model_extrapolation"
        cloned["source_cell"] = (
            f"post_model_extrapolation:{record.scenario_name}:FY{int(record.fy)}"
        )
        cloned["quarter_composition"] = ""
        cloned["actual_quarters"] = ""
        cloned["forecast_quarters"] = ""
        cloned["residual_vs_official"] = np.nan
        cloned["availability_status"] = "available"
        out_rows.append(cloned)
    if missing_templates:
        raise PostModelExtrapolationError(
            "No FY2030 line-reconciliation template for "
            f"{sorted(missing_templates)[:4]}; the extrapolation cannot invent "
            "row metadata."
        )
    frame = pd.DataFrame(out_rows).reset_index(drop=True)
    frame["forecast_segment"] = POST_MODEL_SEGMENT
    return frame


def post_model_chart_rows(
    chart_rows: pd.DataFrame,
    extrapolation: pd.DataFrame,
) -> pd.DataFrame:
    """Map the extrapolation frame into chart-row-schema june_year rows.

    Only the series the chart publishes are emitted; hidden leaves stay in
    the line reconciliation exactly as they do for FY2026-FY2030. Templates
    are each (scenario, series) FY2030 june_year chart row.
    """

    if extrapolation is None or extrapolation.empty:
        return pd.DataFrame(columns=chart_rows.columns)
    annual = chart_rows[
        chart_rows["time_grain"].astype(str).eq("june_year")
        & pd.to_numeric(chart_rows["june_year"], errors="coerce").eq(ANCHOR_FY)
        & chart_rows["scenario_role"].astype(str).isin(["basecase", "comparison"])
    ]
    templates = {
        (str(row.scenario_name), str(row.series_id)): annual.loc[row.Index]
        for row in annual.itertuples(index=True)
    }
    chart_series = {key[1] for key in templates}
    out_rows: list[pd.Series] = []
    for record in extrapolation.itertuples():
        if str(record.series_id) not in chart_series:
            continue
        template = templates.get((str(record.scenario_name), str(record.series_id)))
        if template is None:
            raise PostModelExtrapolationError(
                f"No FY2030 chart template for {record.scenario_name}/{record.series_id}."
            )
        cloned = template.copy()
        fy = int(record.fy)
        cloned["period"] = f"FY{fy}"
        cloned["target_period"] = f"FY{fy}"
        cloned["june_year"] = fy
        cloned["value"] = float(record.value)
        cloned["value_status"] = POST_MODEL_VALUE_STATUS
        cloned["formula"] = str(record.formula)
        cloned["source"] = "post_model_structural_extrapolation"
        cloned["source_file"] = "post_model_extrapolation"
        cloned["source_cell"] = (
            f"post_model_extrapolation:{record.scenario_name}:FY{fy}"
        )
        cloned["horizon"] = np.nan
        cloned["horizon_scope"] = "post_model_extrapolation"
        cloned["actual_quarters"] = ""
        cloned["forecast_quarters"] = ""
        cloned["quarters_present"] = ""
        cloned["nowcast_flag"] = False
        cloned["anchor_flag"] = False
        out_rows.append(cloned)
    frame = pd.DataFrame(out_rows).reset_index(drop=True)
    frame["forecast_segment"] = POST_MODEL_SEGMENT
    return frame


def stamp_forecast_segments(chart_rows: pd.DataFrame) -> pd.DataFrame:
    """Label every chart row's segment explicitly.

    Current-role forecast rows through FY2030/H20 are the econometric
    segment; post-model rows already carry their own label; actuals and the
    official comparator are outside the segmentation and stay empty.
    """

    out = chart_rows.copy()
    if "forecast_segment" not in out.columns:
        out["forecast_segment"] = ""
    out["forecast_segment"] = out["forecast_segment"].fillna("").astype(str)
    current = out["scenario_role"].astype(str).isin(["basecase", "comparison"])
    unlabelled = current & out["forecast_segment"].eq("")
    is_forecast = out["row_type"].astype(str).eq("future_forecast") if "row_type" in out.columns else current
    out.loc[unlabelled & is_forecast, "forecast_segment"] = ECONOMETRIC_SEGMENT
    return out

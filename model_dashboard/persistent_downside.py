"""The governed Persistent downside scenario: a monotone negative wedge.

The three Middle East conflict severities are source-faithful TEMPORARY
shocks: their governed fuel and GDP assumptions recover, so their revenue
paths converge back to the central case by construction. Presenting one of
them as a ten-year downside therefore produces the confusing "bad now, rosy
later" story: the cumulative shortfall builds for a few years and then
recovers toward zero because the underlying assumptions recover.

This module supplies the scenario that risk story actually needs. It is a
display-layer derived scenario - like the conflict traces it is built ON TOP
of the fully-overlaid central chart rows, so EV uptake, eRUC and FED/RUC
policy timing all compose with it exactly as they do with every other trace -
defined by a central-relative wedge rather than by a second level path:

    w_t = log(central_t / downside_t)          (so downside_t = central_t * exp(-w_t))

Construction, per demand-driven series:

SHORT RUN (through FY2030, the econometric window)
    The High conflict severity's own econometric response, RATCHETED: the
    downside ratio at each year is the worst ratio seen so far, so the path
    follows the High shock down but never takes the recovery its governed
    fuel path assumes. "Higher fuel prices for longer" without inventing a
    new short-run model response.

LONG RUN (FY2031-FY2050)
    The per-series seam wedge (the ratcheted FY2030 wedge) moves smoothly to
    one explicit governed TERMINAL wedge under a cubic smoothstep completing
    at FY2042, and is exactly flat from FY2043 to FY2050. The smoothstep's
    zero endpoint slopes give level-and-growth continuity at the FY2030/31
    seam and the final flattening the risk story needs, with no rebound.

The terminal wedge is calibrated against the committed conditional
forecast-error evidence: it sits between the lower-50% and lower-80% band
wedges of Total NLTF net revenue at the last backtest-supported year
(FY2030), whose multipliers the uncertainty layer holds flat (plateau) over
the long run. The bands are a SEVERITY BENCHMARK here, never the path: they
are conditional model-error bands and deliberately exclude Treasury-driver
uncertainty, so tracing a band directly would double-count.

Hard gates, enforced at construction and re-tested in CI:

- downside / central <= 1 for every demand series and every aggregate from
  the first shocked year on (the ratio never crosses one);
- the per-series factor path is monotone non-increasing (the cumulative
  shortfall can widen or plateau, never recover toward zero);
- no sign changes or oscillation - monotonicity makes them impossible;
- exact flatness across the terminal FY2043-FY2050 window;
- aggregates are rebuilt additively from their demand-leaf deltas, so the
  wedge never scales an official carried fixed line (admin, refunds, MVR,
  TUC, LPG/CNG, Heavy BEV stay central) and closure survives by construction.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .conflict_fuel_paths import BASE_SCENARIO_ID, conflict_scenario_id

__all__ = [
    "PERSISTENT_DOWNSIDE_SCENARIO_ID",
    "PERSISTENT_DOWNSIDE_TRACE_NAME",
    "PERSISTENT_DOWNSIDE_NOTE",
    "PERSISTENT_DOWNSIDE_TERMINAL_WEDGE",
    "DOWNSIDE_RAMP_ANCHOR_FY",
    "DOWNSIDE_RAMP_COMPLETION_FY",
    "DOWNSIDE_TERMINAL_FLAT_FIRST_FY",
    "DOWNSIDE_LAST_FY",
    "DEMAND_LEAF_SERIES",
    "PersistentDownsideError",
    "apply_persistent_downside_to_chart_rows",
    "build_persistent_downside_annual_values",
    "downside_wedge_path",
    "persistent_downside_band_evidence",
    "validate_persistent_downside_values",
]

PERSISTENT_DOWNSIDE_SCENARIO_ID = "persistent_downside"
PERSISTENT_DOWNSIDE_TRACE_NAME = "Persistent downside"
PERSISTENT_DOWNSIDE_NOTE = (
    "Persistent downside. Short run: the High conflict severity's econometric "
    "response held at its worst-so-far (no assumed fuel-price recovery). Long "
    "run: the central-relative wedge moves smoothly to a governed terminal "
    "wedge by FY2042 and stays exactly flat to FY2050. The terminal wedge is "
    "benchmarked between the lower-50% and lower-80% conditional forecast-"
    "error bands at FY2030 (plateau-held); the bands are a severity check, "
    "not the path. The downside/central ratio never crosses one and the "
    "cumulative shortfall never recovers toward zero. Official carried fixed "
    "lines (admin, refunds, MVR, TUC, LPG, CNG, Heavy BEV) stay central; "
    "aggregates are rebuilt from the affected demand leaves."
)

# The governed terminal wedge on every demand-driven series:
#   downside_terminal = central * exp(-PERSISTENT_DOWNSIDE_TERMINAL_WEDGE)
# 0.105 is the midpoint of the Total-NLTF lower-band evidence wedges at
# FY2030, the last backtest-supported year: -log(lower50/central) ~= 0.0868
# and -log(lower80/central) ~= 0.1219 on the committed uncertainty pack. The
# gate in persistent_downside_band_evidence re-derives both bounds from the
# committed band rows, so a rebuilt uncertainty pack that moved them would
# fail closed rather than silently re-rating the scenario's severity.
PERSISTENT_DOWNSIDE_TERMINAL_WEDGE = 0.105

DOWNSIDE_RAMP_ANCHOR_FY = 2030
DOWNSIDE_RAMP_COMPLETION_FY = 2042
DOWNSIDE_TERMINAL_FLAT_FIRST_FY = 2043
DOWNSIDE_LAST_FY = 2050

# The modelled demand leaves the wedge applies to. Everything else in the
# chart-row inventory is either an official carried fixed line (stays
# central) or an aggregate (rebuilt from these leaves).
DEMAND_LEAF_SERIES: tuple[str, ...] = (
    "ped_vkt_per_capita",
    "light_petrol_vkt",
    "ped_volume",
    "gross_ped_revenue",
    "heavy_ruc_net_km",
    "heavy_ruc_net_revenue",
    "light_ruc_net_km",
    "light_bev_ruc_net_km",
    "phev_ruc_net_km",
    "current_light_ruc_conventional_modelled_km",
    "light_ruc_net_revenue",
    "light_bev_ruc_net_revenue",
    "phev_ruc_net_revenue",
)

_PED_REVENUE_LEAVES = ("gross_ped_revenue",)
_RUC_REVENUE_LEAVES = (
    "light_ruc_net_revenue",
    "heavy_ruc_net_revenue",
    "light_bev_ruc_net_revenue",
    "phev_ruc_net_revenue",
)

_MONOTONE_TOLERANCE = 1e-9
_FLAT_TOLERANCE = 1e-12
_RATIO_TOLERANCE = 1e-12


class PersistentDownsideError(ValueError):
    """A governed input for the persistent downside is missing or unusable."""


def _smoothstep(u: np.ndarray) -> np.ndarray:
    clipped = np.clip(u, 0.0, 1.0)
    return 3.0 * clipped**2 - 2.0 * clipped**3


def downside_wedge_path(
    seam_wedge: float,
    *,
    first_fy: int = DOWNSIDE_RAMP_ANCHOR_FY + 1,
    last_fy: int = DOWNSIDE_LAST_FY,
    terminal_wedge: float = PERSISTENT_DOWNSIDE_TERMINAL_WEDGE,
) -> pd.DataFrame:
    """Per-FY wedge from the seam to the flat terminal, with governance columns.

    ``w_fy = seam + (terminal - seam) * smoothstep((fy - 2030) / (2042 - 2030))``
    for FY2031-FY2042, then exactly the terminal wedge to FY2050. The
    smoothstep has zero slope at both ends: the path leaves the econometric
    seam without a kink and arrives at the terminal level already flat, which
    is the "one final soften tail" - not a rebound - the scenario specifies.
    """

    seam = float(seam_wedge)
    terminal = float(terminal_wedge)
    if not np.isfinite(seam) or seam < 0.0:
        raise PersistentDownsideError(
            f"seam wedge {seam_wedge!r} must be finite and non-negative: a "
            "downside cannot begin above the central path."
        )
    if not np.isfinite(terminal) or terminal <= 0.0:
        raise PersistentDownsideError(
            f"terminal wedge {terminal_wedge!r} must be finite and positive."
        )
    fys = np.arange(int(first_fy), int(last_fy) + 1, dtype=int)
    span = float(DOWNSIDE_RAMP_COMPLETION_FY - DOWNSIDE_RAMP_ANCHOR_FY)
    u = (fys.astype(float) - float(DOWNSIDE_RAMP_ANCHOR_FY)) / span
    ramp = _smoothstep(u)
    w = seam + (terminal - seam) * ramp
    frame = pd.DataFrame(
        {
            "fy": fys,
            "u": np.clip(u, 0.0, 1.0),
            "ramp": ramp,
            "w": w,
            "factor": np.exp(-w),
            "seam_wedge": seam,
            "terminal_wedge": terminal,
            "phase": np.where(
                fys >= DOWNSIDE_TERMINAL_FLAT_FIRST_FY, "terminal_flat", "handover_ramp"
            ),
        }
    )
    _guard_wedge_path(frame)
    return frame


def _guard_wedge_path(frame: pd.DataFrame) -> None:
    w = frame["w"].to_numpy(dtype=float)
    if not np.isfinite(w).all() or (w < -_RATIO_TOLERANCE).any():
        raise PersistentDownsideError("wedge path is non-finite or negative.")
    steps = np.diff(w)
    if (steps > _MONOTONE_TOLERANCE).any() and (steps < -_MONOTONE_TOLERANCE).any():
        raise PersistentDownsideError(
            "wedge path oscillates: it must move monotonically from the seam "
            "to the terminal wedge."
        )
    flat = frame.loc[frame["fy"] >= DOWNSIDE_TERMINAL_FLAT_FIRST_FY, "w"].to_numpy(
        dtype=float
    )
    if len(flat) and (np.abs(flat - flat[0]) > _FLAT_TOLERANCE).any():
        raise PersistentDownsideError(
            f"wedge path is not exactly flat from FY{DOWNSIDE_TERMINAL_FLAT_FIRST_FY}."
        )


def _annual_value_lookup(
    chart_rows: pd.DataFrame, scenario_name: str
) -> dict[tuple[str, int], float]:
    scoped = chart_rows[
        chart_rows["scenario_name"].astype(str).eq(scenario_name)
        & chart_rows["time_grain"].astype(str).eq("june_year")
    ]
    lookup: dict[tuple[str, int], float] = {}
    for row in scoped.itertuples():
        fy = pd.to_numeric(pd.Series([row.june_year]), errors="coerce").iloc[0]
        value = pd.to_numeric(pd.Series([row.value]), errors="coerce").iloc[0]
        if pd.notna(fy) and pd.notna(value):
            lookup[(str(row.series_id), int(fy))] = float(value)
    return lookup


def build_persistent_downside_annual_values(
    base_values: dict[tuple[str, int], float],
    high_values: dict[tuple[str, int], float],
    *,
    aggregate_series: dict[str, str],
    terminal_wedge: float = PERSISTENT_DOWNSIDE_TERMINAL_WEDGE,
) -> pd.DataFrame:
    """(series_id, fy, value, factor, wedge, phase, basis) for every series.

    ``aggregate_series`` maps an aggregate series_id to its rebuild basis:
    ``"ped"``, ``"ruc"`` or ``"total"``. Every demand leaf gets the ratchet +
    wedge construction; every listed aggregate is rebuilt additively from its
    leaf deltas; everything else present in ``base_values`` stays central
    (factor exactly 1) as an official carried fixed line.
    """

    fys = sorted({fy for _, fy in base_values})
    if not fys:
        raise PersistentDownsideError("central chart rows carry no annual values.")
    last_short_run_fy = min(DOWNSIDE_RAMP_ANCHOR_FY, max(fys))
    ramp_fys = [fy for fy in fys if fy > DOWNSIDE_RAMP_ANCHOR_FY]

    rows: list[dict[str, Any]] = []
    leaf_values: dict[tuple[str, int], float] = {}
    for series in DEMAND_LEAF_SERIES:
        series_fys = [fy for fy in fys if (series, fy) in base_values]
        if not series_fys:
            continue
        short_run = [fy for fy in series_fys if fy <= last_short_run_fy]
        missing_high = [
            fy for fy in short_run if (series, fy) not in high_values
        ]
        if missing_high:
            raise PersistentDownsideError(
                f"{series}: the High conflict trace has no annual values for "
                f"FY{missing_high[:4]}; the downside short run cannot be built."
            )
        ratchet = 1.0
        for fy in short_run:
            base = base_values[(series, fy)]
            if base <= 0.0:
                raise PersistentDownsideError(
                    f"{series} FY{fy}: central value {base!r} must be positive."
                )
            ratio = high_values[(series, fy)] / base
            ratchet = min(ratchet, min(ratio, 1.0))
            value = base * ratchet
            leaf_values[(series, fy)] = value
            rows.append(
                {
                    "series_id": series,
                    "fy": fy,
                    "value": value,
                    "factor": ratchet,
                    "wedge": -float(np.log(ratchet)),
                    "phase": "econometric_ratchet",
                    "basis": "high_severity_response_ratcheted_no_recovery",
                }
            )
        seam_wedge = -float(np.log(ratchet))
        if ramp_fys:
            wedge = downside_wedge_path(
                seam_wedge,
                first_fy=min(ramp_fys),
                last_fy=max(ramp_fys),
                terminal_wedge=terminal_wedge,
            ).set_index("fy")
            for fy in ramp_fys:
                if (series, fy) not in base_values:
                    continue
                base = base_values[(series, fy)]
                if base <= 0.0:
                    raise PersistentDownsideError(
                        f"{series} FY{fy}: central value {base!r} must be positive."
                    )
                factor = float(wedge.at[fy, "factor"])
                value = base * factor
                leaf_values[(series, fy)] = value
                rows.append(
                    {
                        "series_id": series,
                        "fy": fy,
                        "value": value,
                        "factor": factor,
                        "wedge": float(wedge.at[fy, "w"]),
                        "phase": str(wedge.at[fy, "phase"]),
                        "basis": "seam_wedge_to_governed_terminal_smoothstep",
                    }
                )

    def _leaf_delta(leaves: tuple[str, ...], fy: int) -> float:
        delta = 0.0
        for series in leaves:
            base = base_values.get((series, fy))
            downside = leaf_values.get((series, fy))
            if base is not None and downside is not None:
                delta += downside - base
        return delta

    for series, basis_kind in aggregate_series.items():
        for fy in fys:
            base = base_values.get((series, fy))
            if base is None:
                continue
            if basis_kind == "ped":
                delta = _leaf_delta(_PED_REVENUE_LEAVES, fy)
            elif basis_kind == "ruc":
                delta = _leaf_delta(_RUC_REVENUE_LEAVES, fy)
            elif basis_kind == "total":
                delta = _leaf_delta(_PED_REVENUE_LEAVES, fy) + _leaf_delta(
                    _RUC_REVENUE_LEAVES, fy
                )
            else:
                raise PersistentDownsideError(
                    f"unknown aggregate basis {basis_kind!r} for {series!r}."
                )
            value = base + delta
            rows.append(
                {
                    "series_id": series,
                    "fy": fy,
                    "value": value,
                    "factor": value / base if abs(base) > 1e-12 else 1.0,
                    "wedge": -float(np.log(value / base))
                    if base > 0.0 and value > 0.0
                    else np.nan,
                    "phase": "aggregate_rebuild",
                    "basis": f"additive_{basis_kind}_leaf_delta",
                }
            )

    handled = set(DEMAND_LEAF_SERIES) | set(aggregate_series)
    for (series, fy), base in base_values.items():
        if series in handled:
            continue
        rows.append(
            {
                "series_id": series,
                "fy": fy,
                "value": base,
                "factor": 1.0,
                "wedge": 0.0,
                "phase": "carried_fixed_line",
                "basis": "official_carried_line_stays_central",
            }
        )

    frame = pd.DataFrame(rows)
    validate_persistent_downside_values(frame)
    return frame


def validate_persistent_downside_values(frame: pd.DataFrame) -> None:
    """The scenario's hard gates, enforced at construction.

    Ratio never above one once shocked, factors monotone non-increasing (the
    cumulative shortfall widens or plateaus, never recovers), exact terminal
    flatness, and no oscillation - checked per demand leaf AND per rebuilt
    aggregate, so the story the totals tell is the story the gates protect.
    """

    if frame is None or frame.empty:
        raise PersistentDownsideError("persistent downside produced no rows.")
    scoped = frame[~frame["phase"].astype(str).eq("carried_fixed_line")]
    leaf_phases = {"econometric_ratchet", "handover_ramp", "terminal_flat"}
    for series, group in scoped.groupby("series_id", sort=False):
        ordered = group.sort_values("fy")
        factors = ordered["factor"].to_numpy(dtype=float)
        fys = ordered["fy"].to_numpy(dtype=int)
        if not np.isfinite(factors).all() or (factors <= 0.0).any():
            raise PersistentDownsideError(
                f"{series}: downside factor is non-finite or non-positive."
            )
        # Gate 1, every shocked series AND every rebuilt aggregate: the
        # downside/central ratio never crosses one, so no annual delta can
        # turn positive and the cumulative shortfall can never shrink.
        if (factors > 1.0 + _RATIO_TOLERANCE).any():
            worst_fy = int(fys[int(np.argmax(factors))])
            raise PersistentDownsideError(
                f"{series}: downside/central ratio exceeds 1 at FY{worst_fy} - "
                "the downside crossed above the central path."
            )
        # Gates 2 and 3 are LEAF properties: an aggregate's factor is a
        # base-share-weighted mean of leaf factors plus the unchanged fixed
        # lines, so composition drift can legitimately move it while every
        # annual delta stays negative.
        if not ordered["phase"].isin(leaf_phases).all():
            continue
        if (np.diff(factors) > _MONOTONE_TOLERANCE).any():
            raise PersistentDownsideError(
                f"{series}: downside factor path recovers toward the central "
                "path - the cumulative shortfall must widen or plateau, never "
                "shrink."
            )
        flat = ordered.loc[
            ordered["fy"] >= DOWNSIDE_TERMINAL_FLAT_FIRST_FY, "factor"
        ].to_numpy(dtype=float)
        if len(flat) and (np.abs(flat - flat[0]) > _FLAT_TOLERANCE).any():
            raise PersistentDownsideError(
                f"{series}: terminal FY{DOWNSIDE_TERMINAL_FLAT_FIRST_FY}-"
                f"FY{DOWNSIDE_LAST_FY} window is not flat."
            )


def persistent_downside_band_evidence(
    band_rows: pd.DataFrame,
    downside_values: pd.DataFrame,
    *,
    series_id: str = "total_nltf_net_revenue",
    benchmark_fy: int = DOWNSIDE_RAMP_ANCHOR_FY,
) -> pd.DataFrame:
    """The severity benchmark: the terminal wedge versus the band evidence.

    Derives ``-log(lower50/central)`` and ``-log(lower80/central)`` for the
    benchmark year from the committed conditional-band rows and reports where
    the governed terminal wedge and the realised FY2035/FY2042 wedges sit
    against them. The gate: the terminal wedge must lie WITHIN the
    [lower50, lower80] evidence wedge range - deep enough to be a real
    downside, never deeper than the model-error evidence supports.
    """

    scoped = band_rows[
        band_rows["series_id"].astype(str).eq(series_id)
        & pd.to_numeric(band_rows["FY"], errors="coerce").eq(int(benchmark_fy))
    ]
    if scoped.empty:
        raise PersistentDownsideError(
            f"band rows carry no {series_id} evidence at FY{benchmark_fy}."
        )
    central = float(pd.to_numeric(scoped["central"], errors="coerce").iloc[0])
    lower50 = float(pd.to_numeric(scoped["lower50"], errors="coerce").iloc[0])
    lower80 = float(pd.to_numeric(scoped["lower80"], errors="coerce").iloc[0])
    if min(central, lower50, lower80) <= 0.0:
        raise PersistentDownsideError("band evidence values must be positive.")
    lower50_wedge = -float(np.log(lower50 / central))
    lower80_wedge = -float(np.log(lower80 / central))
    terminal = float(PERSISTENT_DOWNSIDE_TERMINAL_WEDGE)
    within = lower50_wedge - 1e-9 <= terminal <= lower80_wedge + 1e-9

    total = downside_values[
        downside_values["series_id"].astype(str).eq(series_id)
    ].set_index("fy")
    rows = [
        {
            "measure": "lower50_evidence_wedge",
            "fy": benchmark_fy,
            "value": lower50_wedge,
            "note": "-log(lower50/central) at the last backtest-supported year",
        },
        {
            "measure": "lower80_evidence_wedge",
            "fy": benchmark_fy,
            "value": lower80_wedge,
            "note": "-log(lower80/central), plateau-held over the long run",
        },
        {
            "measure": "governed_terminal_wedge",
            "fy": DOWNSIDE_RAMP_COMPLETION_FY,
            "value": terminal,
            "note": "PERSISTENT_DOWNSIDE_TERMINAL_WEDGE",
        },
        {
            "measure": "terminal_within_band_evidence_range",
            "fy": DOWNSIDE_RAMP_COMPLETION_FY,
            "value": float(within),
            "note": "gate: lower50 <= terminal <= lower80",
        },
    ]
    for fy in (2035, DOWNSIDE_RAMP_COMPLETION_FY, DOWNSIDE_LAST_FY):
        if fy in total.index:
            rows.append(
                {
                    "measure": "realised_total_wedge",
                    "fy": fy,
                    "value": float(total.at[fy, "wedge"]),
                    "note": "-log(downside/central) on Total NLTF net revenue",
                }
            )
    frame = pd.DataFrame(rows)
    if not within:
        raise PersistentDownsideError(
            f"terminal wedge {terminal:.4f} sits outside the band evidence "
            f"range [{lower50_wedge:.4f}, {lower80_wedge:.4f}] - recalibrate "
            "the governed constant against the committed uncertainty pack."
        )
    return frame


def apply_persistent_downside_to_chart_rows(
    chart_rows: pd.DataFrame,
    *,
    aggregate_series: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Append the Persistent downside trace to fully-overlaid chart rows.

    Derived at the END of the overlay chain from the displayed central
    (``current_basecase``) and High conflict rows, so every upstream overlay -
    uptake, eRUC, FED/RUC policy timing, sensitivities - composes with the
    downside exactly as it composed with the sides it is derived from, and
    policy timing stays separately attributable. Annual-grain only, like the
    official comparator: the wedge is an annual construct and must never
    imply quarterly precision it does not have. Idempotent.
    """

    if chart_rows is None or chart_rows.empty:
        return chart_rows, pd.DataFrame()
    if aggregate_series is None:
        from .ev_uptake_levers import (
            FED_AGGREGATE_SERIES,
            RUC_AGGREGATE_SERIES,
            TOTAL_AGGREGATE_SERIES,
        )

        aggregate_series = {
            **{series: "ruc" for series in RUC_AGGREGATE_SERIES},
            **{series: "ped" for series in FED_AGGREGATE_SERIES},
            **{series: "total" for series in TOTAL_AGGREGATE_SERIES},
        }

    source = chart_rows[
        ~chart_rows["scenario_name"].astype(str).eq(PERSISTENT_DOWNSIDE_SCENARIO_ID)
    ].copy()
    high_scenario = conflict_scenario_id("high")
    base_values = _annual_value_lookup(source, BASE_SCENARIO_ID)
    high_values = _annual_value_lookup(source, high_scenario)
    if not base_values:
        raise PersistentDownsideError(
            f"chart rows carry no annual {BASE_SCENARIO_ID!r} values."
        )
    if not high_values:
        raise PersistentDownsideError(
            f"chart rows carry no annual {high_scenario!r} values; the "
            "persistent downside seam needs the High conflict response and "
            "must fail closed rather than invent one."
        )

    values = build_persistent_downside_annual_values(
        base_values, high_values, aggregate_series=aggregate_series
    )
    value_lookup = {
        (str(row.series_id), int(row.fy)): (
            float(row.value),
            float(row.factor),
            str(row.phase),
            str(row.basis),
        )
        for row in values.itertuples()
    }

    template = source[
        source["scenario_name"].astype(str).eq(BASE_SCENARIO_ID)
        & source["time_grain"].astype(str).eq("june_year")
    ].copy()
    keep: list[int] = []
    downside_meta: dict[int, tuple[float, float, str, str]] = {}
    for index, row in template.iterrows():
        fy = pd.to_numeric(pd.Series([row.get("june_year")]), errors="coerce").iloc[0]
        if pd.isna(fy):
            continue
        meta = value_lookup.get((str(row.get("series_id")), int(fy)))
        if meta is None:
            continue
        keep.append(index)
        downside_meta[index] = meta

    scenario = template.loc[keep].copy()
    scenario["value"] = [downside_meta[index][0] for index in keep]
    scenario["scenario_name"] = PERSISTENT_DOWNSIDE_SCENARIO_ID
    scenario["scenario_role"] = "comparison"
    scenario["trace_name"] = PERSISTENT_DOWNSIDE_TRACE_NAME
    if "trace_type" in scenario.columns:
        scenario["trace_type"] = "derived persistent downside scenario"
    if "trace_role" in scenario.columns:
        scenario["trace_role"] = "comparison"
    if "trace_source" in scenario.columns:
        scenario["trace_source"] = "central-relative monotone wedge"
    scenario["persistent_downside_scenario"] = True
    scenario["persistent_downside_note"] = PERSISTENT_DOWNSIDE_NOTE
    if "canonical_scenario_key" in scenario.columns:
        scenario["canonical_scenario_key"] = PERSISTENT_DOWNSIDE_SCENARIO_ID
    if "canonical_join_key" in scenario.columns:
        period_key = scenario.get(
            "canonical_period_key", scenario.get("period", pd.Series("", index=scenario.index))
        ).astype(str)
        stream_key = scenario.get(
            "canonical_stream_key", scenario.get("stream", pd.Series("", index=scenario.index))
        ).astype(str)
        scenario["canonical_join_key"] = (
            stream_key + "|" + period_key + "|" + PERSISTENT_DOWNSIDE_SCENARIO_ID
        )

    audit_rows: list[dict[str, Any]] = []
    for index in keep:
        value, factor, phase, basis = downside_meta[index]
        row = template.loc[index]
        base = pd.to_numeric(pd.Series([row.get("value")]), errors="coerce").iloc[0]
        audit_rows.append(
            {
                "scenario_name": PERSISTENT_DOWNSIDE_SCENARIO_ID,
                "trace_name": PERSISTENT_DOWNSIDE_TRACE_NAME,
                "series_id": str(row.get("series_id") or ""),
                "june_year": int(
                    pd.to_numeric(pd.Series([row.get("june_year")]), errors="coerce").iloc[0]
                ),
                "period": str(row.get("period") or ""),
                "central_value": float(base) if pd.notna(base) else np.nan,
                "downside_value": value,
                "factor": factor,
                "wedge": -float(np.log(factor)) if factor > 0.0 else np.nan,
                "phase": phase,
                "transformation_basis": basis,
                "scenario_note": PERSISTENT_DOWNSIDE_NOTE,
            }
        )

    combined = pd.concat([source, scenario], ignore_index=True, sort=False)
    return combined, pd.DataFrame(audit_rows)

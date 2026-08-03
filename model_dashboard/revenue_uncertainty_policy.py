"""Propagate the committed uncertainty draws through a policy-specific centre.

The PR #15 methodology is unchanged and must stay unchanged: three parent
shocks, one Gaussian copula on a shrunk Spearman rank correlation, marginals
quantile-mapped onto the governed June-year targets, the FY2030 evidence seam,
the FY2031-FY2050 plateau, and ``FORMULA_DEFINITIONS`` evaluated draw by draw.
Nothing here re-estimates any of that.

What changes per policy state is only the CENTRE the draws are applied to.  A
band is a distribution around a central path; if the 12c policy moves that
path, the band has to move with it, and it has to move by propagating the same
draws through the same identities - not by rescaling yesterday's aggregate
endpoints by a ratio, which would assert a dependence structure nobody chose
and would break the identities at the same time.

The converse matters just as much.  Where a policy leaves a series genuinely
untouched - MVR revenue, or VKT per capita beyond the fixed-finalist replay
window - the central values are identical, so the same draws produce identical
bounds.  Unchanged bounds there are the CORRECT answer, not a missing feature,
and they arise by construction rather than by copying a frame.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .mbu26_source_spine import FORMULA_DEFINITIONS
from .revenue_uncertainty import QuantileMultipliers, evidence_state_for_fy
from .revenue_uncertainty_draws import DRAW_COUNT, DRAW_SEED

__all__ = [
    "FIXED_LEAVES",
    "FORMULA_TOLERANCE",
    "HEAVY_BEV_PROXY_LEAVES",
    "HEAVY_LEAVES",
    "LIGHT_LEAVES",
    "MVR_PROXY_LEAVES",
    "PARENT_OF_LEAF",
    "PED_LEAVES",
    "REPORTED_SERIES",
    "band_dependency_rows",
    "band_rows_for_policy_state",
    "evaluate_formulas",
    "formula_residual_rows",
    "mvr_proxy_factor",
]

FORMULA_TOLERANCE = 1e-6

# Leaf -> parent shock. Identical to the committed offline pack's assignment;
# the policy layer changes the central value each leaf is multiplied by, never
# which shock drives it.
PED_LEAVES = (
    "ped_vkt_per_capita", "ped_volume", "light_petrol_vkt",
    "gross_ped_revenue", "fed_refunds",
)
LIGHT_LEAVES = (
    "light_ruc_net_km", "light_ruc_net_revenue",
    "light_bev_ruc_net_km", "light_bev_ruc_net_revenue",
    "phev_ruc_net_km", "phev_ruc_net_revenue",
    "current_light_ruc_conventional_modelled_km",
)
HEAVY_LEAVES = ("heavy_ruc_net_km", "heavy_ruc_net_revenue")
HEAVY_BEV_PROXY_LEAVES = ("heavy_bev_ruc_net_km", "heavy_bev_ruc_net_revenue")
MVR_PROXY_LEAVES = ("mr1_revenue", "mr2_revenue")
FIXED_LEAVES = (
    "ruc_admin_revenue", "ruc_refunds", "mvr_admin_revenue", "mvr_refunds",
    "coo_revenue", "gross_lpg_revenue", "gross_cng_revenue", "tuc_net_revenue",
)
PARENT_OF_LEAF: dict[str, str] = {
    **{leaf: "PED" for leaf in PED_LEAVES},
    **{leaf: "LIGHT_RUC" for leaf in LIGHT_LEAVES},
    **{leaf: "HEAVY_RUC" for leaf in HEAVY_LEAVES},
    **{leaf: "HEAVY_RUC_PROXY" for leaf in HEAVY_BEV_PROXY_LEAVES},
    **{leaf: "MVR_PROXY" for leaf in MVR_PROXY_LEAVES},
    **{leaf: "FIXED" for leaf in FIXED_LEAVES},
}
FORMULA_OUTPUTS = tuple(str(d["output_series_id"]) for d in FORMULA_DEFINITIONS)
REPORTED_SERIES = tuple(dict.fromkeys((*PARENT_OF_LEAF.keys(), *FORMULA_OUTPUTS)))


def evaluate_formulas(leaf_draws: dict[str, np.ndarray], draws: int) -> dict[str, np.ndarray]:
    """Evaluate FORMULA_DEFINITIONS in registry order, draw by draw."""
    values: dict[str, np.ndarray] = dict(leaf_draws)
    for definition in FORMULA_DEFINITIONS:
        output = str(definition["output_series_id"])
        total = np.zeros(draws)
        complete = True
        for term, sign in definition["terms"]:
            series = values.get(str(term))
            if series is None:
                complete = False
                break
            total = total + float(sign) * series
        if complete:
            values[output] = total
    return values


def mvr_proxy_factor(multipliers: QuantileMultipliers, *, draws: int = DRAW_COUNT) -> np.ndarray:
    """The MVR vintage-revision factor draws.

    Given its own independent ordering: it is a vintage revision, not a model
    error, and has no measured relationship to the three forecast streams.
    """
    factor = np.exp(
        np.sort(
            np.quantile(
                np.array(
                    [
                        multipliers.q10,
                        multipliers.q25,
                        multipliers.median,
                        multipliers.q75,
                        multipliers.q90,
                    ]
                ),
                np.linspace(0.0, 1.0, draws),
            )
        )
    )
    return factor[np.random.default_rng(DRAW_SEED + 1).permutation(draws)]


def _leaf_draws(
    central: dict[tuple[str, int], float],
    factors: dict[str, np.ndarray],
    mvr_factor: np.ndarray,
    fy: int,
    draws: int,
) -> dict[str, np.ndarray]:
    leaf_draws: dict[str, np.ndarray] = {}
    for leaf, parent in PARENT_OF_LEAF.items():
        value = central.get((leaf, fy))
        if value is None:
            continue
        if parent == "FIXED":
            factor = np.ones(draws)
        elif parent == "MVR_PROXY":
            factor = mvr_factor
        elif parent == "HEAVY_RUC_PROXY":
            factor = factors["HEAVY_RUC"]
        else:
            factor = factors[parent]
        leaf_draws[leaf] = value * factor
    return leaf_draws


def formula_residual_rows(
    evaluated: dict[str, np.ndarray], fy: int, draws: int
) -> list[dict[str, Any]]:
    """Identity closure checked on EVERY draw, not just at the percentiles."""
    rows: list[dict[str, Any]] = []
    for definition in FORMULA_DEFINITIONS:
        output = str(definition["output_series_id"])
        if output not in evaluated:
            continue
        recomputed = np.zeros(draws)
        complete = True
        for term, sign in definition["terms"]:
            if str(term) not in evaluated:
                complete = False
                break
            recomputed = recomputed + float(sign) * evaluated[str(term)]
        if not complete:
            continue
        worst = float(np.max(np.abs(recomputed - evaluated[output])))
        rows.append(
            {
                "FY": fy,
                "output_series_id": output,
                "expression": definition["expression"],
                "draws_checked": draws,
                "max_abs_residual": worst,
                "closes": bool(worst <= FORMULA_TOLERANCE),
            }
        )
    return rows


def band_rows_for_policy_state(
    *,
    central: dict[tuple[str, int], float],
    parent_draws: dict[int, dict[str, np.ndarray]],
    mvr_factor: np.ndarray,
    first_fy: int,
    final_fy: int,
    engine: str,
    policy_state: str,
    scenario_key_digest: str,
    extra_keys: dict[str, Any] | None = None,
    draws: int = DRAW_COUNT,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(band rows, draw-level residual rows) for one policy state.

    ``central`` is the ONLY policy-dependent input. The parent draws, the
    copula ordering, the quantile map and the plateau all arrive already
    built, so two policy states share one joint state per draw index and the
    difference between their bands is exactly the difference between their
    central paths.
    """
    band_rows: list[dict[str, Any]] = []
    residual_rows: list[dict[str, Any]] = []
    keys = dict(extra_keys or {})

    for fy in range(first_fy, final_fy + 1):
        factors = parent_draws.get(fy)
        if not factors:
            continue
        leaf_draws = _leaf_draws(central, factors, mvr_factor, fy, draws)
        evaluated = evaluate_formulas(leaf_draws, draws)

        for row in formula_residual_rows(evaluated, fy, draws):
            residual_rows.append({**keys, "engine": engine, "policy_state": policy_state, **row})

        for series in REPORTED_SERIES:
            if series not in evaluated:
                continue
            sample = evaluated[series]
            centre = central.get((series, fy))
            if centre is None:
                centre = float(np.median(sample))
            q10, q25, q50, q75, q90 = np.quantile(sample, [0.10, 0.25, 0.50, 0.75, 0.90])
            band_rows.append(
                {
                    **keys,
                    "engine": engine,
                    "policy_state": policy_state,
                    "scenario_key_digest": scenario_key_digest,
                    "series_id": series,
                    "FY": fy,
                    "period": f"FY{fy}",
                    "evidence_state": evidence_state_for_fy(fy),
                    "parent_shock": PARENT_OF_LEAF.get(series, "derived"),
                    "central": centre,
                    "lower80": q10,
                    "lower50": q25,
                    "draw_median": q50,
                    "upper50": q75,
                    "upper80": q90,
                    "median_multiplier": q50 / centre if centre else np.nan,
                    "span80_pct": 100.0 * (q90 - q10) / abs(centre) if centre else np.nan,
                    "span50_pct": 100.0 * (q75 - q25) / abs(centre) if centre else np.nan,
                    "probabilistic": True,
                    "method": (
                        "conditional model forecast-error band (actual-driver rolling origin)"
                    ),
                }
            )
    return band_rows, residual_rows


def band_dependency_rows(
    central_by_state: dict[str, dict[tuple[str, int], float]],
    *,
    engine: str,
    reference_state: str,
    activity_of: dict[str, str],
    rate_priced: frozenset[str],
    activity_leaves: frozenset[str] = frozenset(),
) -> pd.DataFrame:
    """Per series and FY: does the policy actually move this band, and why.

    Answers the question BEFORE materialising anything, so an unchanged band
    can be shown to be unchanged because the central path is unchanged - the
    handoff's rule - rather than because the policy layer forgot to reach it.
    """
    rows: list[dict[str, Any]] = []
    reference = central_by_state[reference_state]
    keys = sorted({key for values in central_by_state.values() for key in values})
    for series, fy in keys:
        base = reference.get((series, fy))
        comparisons = {
            state: values.get((series, fy))
            for state, values in central_by_state.items()
            if state != reference_state
        }
        central_changes = any(
            value is not None
            and base is not None
            and abs(float(value) - float(base)) > 1e-9
            for value in comparisons.values()
        )
        # An activity leaf IS its own activity, so a change in it is an
        # activity response - not an identity term inherited from elsewhere.
        # A revenue leaf's activity is the volume it is priced on.
        driver = series if series in activity_leaves else activity_of.get(series, "")
        activity_changes = False
        if driver:
            activity_base = reference.get((driver, fy))
            for state, values in central_by_state.items():
                if state == reference_state:
                    continue
                candidate = values.get((driver, fy))
                if (
                    candidate is not None
                    and activity_base is not None
                    and abs(float(candidate) - float(activity_base)) > 1e-9
                ):
                    activity_changes = True
        rate_changes = bool(central_changes and series in rate_priced)
        if central_changes and not rate_changes and not activity_changes:
            # An aggregate inherits movement from its terms; neither the rate
            # nor the activity of the aggregate itself changed.
            reason = "central moves through a governed identity term"
        elif rate_changes and not activity_changes:
            reason = "rate-priced leaf: the collection rate changed, volume did not"
        elif rate_changes and activity_changes:
            reason = "rate and the modelled activity response both changed"
        elif activity_changes:
            reason = "activity responded inside the fixed-finalist replay window"
        elif series in rate_priced:
            reason = "rate-priced but outside every affected year"
        else:
            reason = "not priced by the fuel rate and no activity response"
        rows.append(
            {
                "engine": engine,
                "series_id": series,
                "FY": fy,
                "reference_policy_state": reference_state,
                "central_changes_under_policy": bool(central_changes),
                "rate_changes_under_policy": bool(rate_changes),
                "activity_changes_under_policy": bool(activity_changes),
                "band_should_change": bool(central_changes),
                "reason": reason,
                **{
                    f"central_{state}": value
                    for state, value in (
                        (reference_state, base),
                        *comparisons.items(),
                    )
                },
            }
        )
    return pd.DataFrame(rows).sort_values(["series_id", "FY"]).reset_index(drop=True)

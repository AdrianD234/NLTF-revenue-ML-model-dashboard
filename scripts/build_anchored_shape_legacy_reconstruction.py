"""Reconstruct the legacy structural logic and separate it from lambda.

Section 2 of the brief. Two independent things are established here, and the
whole point is that they are independent:

1. The workbook `S-curve analysis (F&F)` validates a STRUCTURAL COMPOSITION
   PATH - a logistic BEV-share curve fitted against VFM and cross-checked
   against MBU26. Its four dial parameters are read from cells and its fit
   statistics are re-derived here from the same underlying series, so the
   reconstruction is a check rather than a restatement.

2. Lambda was an ALLOCATION weight that split one migration total between
   petrol VKT and Light RUC. It was never a weight on Current versus MoT, the
   workbook says nothing about it, and it stays retired.

Everything is read from the immutable source workbook and from the committed
lambda investigation evidence. Nothing here becomes runtime code.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import load_workbook

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

OUT = REPO_ROOT / "artifacts" / "anchored_structural_shape_transition"
WORKBOOK = REPO_ROOT / "references" / "MBU26 v VFM202405_outputs_summary_V3 (1).xlsx"
SHEET = "S-curve analysis (F&F)"
LAMBDA_EVIDENCE = REPO_ROOT / "artifacts" / "fleet_allocation_semantics"

# Dial cells, verified by reading the workbook rather than assumed.
DIAL_CELLS = {
    "peak_uptake_speed_share_points_per_year": "C104",
    "curve_ceiling_saturation_share": "C105",
    "steepness": "C106",
    "midpoint_year_of_fastest_uptake": "C107",
}
FIT_CELLS = {
    "straight_line_fit_r_squared": "C148",
    "steepness_read_off_the_line": "C149",
    "steepness_dial": "D149",
    "ceiling_read_off_the_line": "C150",
    "ceiling_dial": "D150",
}

# The calendar-year VFM block, rows 110-145 = 2015-2050.
VFM_BLOCK_FIRST_ROW, VFM_BLOCK_LAST_ROW = 110, 145
VFM_COLUMNS = {
    "light_bev_million_km": "C",
    "phev_million_km": "D",
    "light_ruc_conventional_million_km": "E",
    "light_petrol_million_km": "F",
    "heavy_conventional_million_km": "G",
    "heavy_bev_million_km": "H",
    "conventional_diesel_plus_hybrid": "I",
    "light_ruc_pool_million_km": "J",
    "bev_share_of_pool_base": "K",
    "share_points_added_vs_prior_year": "L",
    "growth_vs_prior_year": "M",
    "headroom_left": "N",
    "taper_law_steepness_x_headroom": "O",
    "bev_share_fast": "P",
    "bev_share_slow": "Q",
    "dashboard_dial_curve": "R",
    "midpoint_share_base": "AD",
    "growth_on_midpoint_basis": "AE",
}

# The June-year comparison block, rows 154-179 = FY2025-FY2050.
JUNE_BLOCK_FIRST_ROW, JUNE_BLOCK_LAST_ROW = 154, 179
JUNE_COLUMNS = {
    "june_year": "B",
    "mot_mbu26_official_bev_share": "C",
    "vfm_base_bev_share": "D",
    "dashboard_dial_curve_bev_share": "E",
    "mot_minus_vfm_base_pp": "F",
    "mot_minus_our_curve_pp": "G",
}


class LegacyReconstructionError(RuntimeError):
    """The workbook does not reproduce its own published structural result."""


@lru_cache(maxsize=2)
def _sheet(data_only: bool):
    """The workbook is 4.5 MB; open each view once and reuse it."""

    return load_workbook(WORKBOOK, data_only=data_only)[SHEET]


def read_dials() -> tuple[dict[str, float], dict[str, float]]:
    values = _sheet(data_only=True)
    formulas = _sheet(data_only=False)
    dials = {name: float(values[cell].value) for name, cell in DIAL_CELLS.items()}
    fits = {name: float(values[cell].value) for name, cell in FIT_CELLS.items()}

    # The steepness dial is DERIVED in the workbook: 4 x speed / ceiling.
    # Re-deriving it here proves the four parameters are mutually consistent
    # rather than four independently typed numbers.
    assert formulas["C106"].value == "=4*C104/C105", formulas["C106"].value
    derived = (
        4.0
        * dials["peak_uptake_speed_share_points_per_year"]
        / dials["curve_ceiling_saturation_share"]
    )
    if abs(derived - dials["steepness"]) > 1e-12:
        raise LegacyReconstructionError(
            f"steepness dial {dials['steepness']!r} does not equal 4*speed/ceiling "
            f"({derived!r})."
        )

    # The logistic itself, read from the cells so the structure is verified
    # rather than assumed from the brief. The workbook evaluates the SAME
    # curve on two year conventions: the June-year block uses the June year
    # directly, while the calendar-year block adds half a year to centre a
    # calendar observation on its June-year equivalent. Both are asserted so a
    # future edit to either convention fails here rather than silently
    # shifting the reconstruction by six months.
    for cell, expected in (
        ("E154", "=$C$105/(1+EXP(-$C$106*(B154-$C$107)))"),
        ("R110", "=$C$105/(1+EXP(-$C$106*(B110+0.5-$C$107)))"),
    ):
        actual = str(formulas[cell].value)
        if actual != expected:
            raise LegacyReconstructionError(
                f"{cell}: the dashboard curve formula is {actual!r}, not the "
                f"expected logistic {expected!r}."
            )
    return dials, fits


def logistic_share(
    year: np.ndarray | float, dials: dict[str, float], *, year_offset: float = 0.0
) -> np.ndarray | float:
    """share = ceiling / (1 + exp(-steepness * (year + offset - midpoint))).

    ``year_offset`` carries the workbook's own year convention: 0.0 for the
    June-year block, +0.5 for the calendar-year block, which centres a calendar
    observation on its June-year equivalent.
    """

    return dials["curve_ceiling_saturation_share"] / (
        1.0
        + np.exp(
            -dials["steepness"]
            * (
                np.asarray(year, dtype=float)
                + year_offset
                - dials["midpoint_year_of_fastest_uptake"]
            )
        )
    )


def _block(columns: dict[str, str], first_row: int, last_row: int) -> pd.DataFrame:
    sheet = _sheet(data_only=True)
    rows: list[dict[str, object]] = []
    for row in range(first_row, last_row + 1):
        record: dict[str, object] = {}
        for name, column in columns.items():
            value = sheet[f"{column}{row}"].value
            record[name] = float(value) if isinstance(value, (int, float)) else value
        record["source_row"] = row
        rows.append(record)
    return pd.DataFrame(rows)


def reconstruct_s_curve(dials: dict[str, float], fits: dict[str, float]) -> tuple[pd.DataFrame, dict[str, float]]:
    """Rebuild the logistic and re-derive the workbook's own fit statistics."""

    calendar = _block(VFM_COLUMNS, VFM_BLOCK_FIRST_ROW, VFM_BLOCK_LAST_ROW)
    calendar.insert(0, "calendar_year", range(2015, 2015 + len(calendar)))

    calendar["reconstructed_dial_curve"] = logistic_share(
        calendar["calendar_year"].to_numpy(), dials, year_offset=0.5
    )
    drift = (
        calendar["reconstructed_dial_curve"] - calendar["dashboard_dial_curve"]
    ).abs()
    if float(drift.max()) > 1e-12:
        raise LegacyReconstructionError(
            f"reconstructed logistic differs from the workbook curve by {float(drift.max()):.3e}."
        )
    calendar["reconstruction_abs_error"] = drift
    calendar["dial_curve_year_offset"] = 0.5

    # Re-derive the published fit. The workbook linearises the logistic:
    # for ds/dt = r*s*(1 - s/K), (ds/dt)/s = r - (r/K)*s, so regressing the
    # mid-point growth rate on the mid-point share gives intercept = r
    # (steepness) and x-intercept = K (ceiling). Recomputing it here from the
    # same two series is what turns the workbook's numbers into a check.
    fit_rows = calendar[
        calendar["calendar_year"].between(2025, 2050)
        & calendar["midpoint_share_base"].notna()
        & calendar["growth_on_midpoint_basis"].notna()
    ]
    x = fit_rows["midpoint_share_base"].to_numpy(dtype=float)
    y = fit_rows["growth_on_midpoint_basis"].to_numpy(dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    correlation = float(np.corrcoef(x, y)[0, 1])
    derived = {
        "recomputed_r_squared": correlation**2,
        "recomputed_steepness_intercept": float(intercept),
        "recomputed_ceiling_x_intercept": float(-intercept / slope),
        "recomputed_slope": float(slope),
        "fit_observations": int(len(x)),
    }
    checks = (
        ("straight_line_fit_r_squared", "recomputed_r_squared"),
        ("steepness_read_off_the_line", "recomputed_steepness_intercept"),
        ("ceiling_read_off_the_line", "recomputed_ceiling_x_intercept"),
    )
    for published_key, recomputed_key in checks:
        published = fits[published_key]
        recomputed = derived[recomputed_key]
        if abs(published - recomputed) > 1e-9:
            raise LegacyReconstructionError(
                f"{published_key}: workbook publishes {published!r} but the same "
                f"regression recomputes {recomputed!r}."
            )
    return calendar, derived


def reconstruct_share_comparison(dials: dict[str, float]) -> pd.DataFrame:
    """MoT MBU26 vs VFM Base vs the dashboard curve, in June years."""

    june = _block(JUNE_COLUMNS, JUNE_BLOCK_FIRST_ROW, JUNE_BLOCK_LAST_ROW)
    june["june_year"] = june["june_year"].astype(int)

    # The same logistic on the June-year convention (no half-year offset).
    june["reconstructed_dial_curve_bev_share"] = logistic_share(
        june["june_year"].to_numpy(), dials, year_offset=0.0
    )
    curve_drift = (
        june["reconstructed_dial_curve_bev_share"] - june["dashboard_dial_curve_bev_share"]
    ).abs()
    if float(curve_drift.max()) > 1e-12:
        raise LegacyReconstructionError(
            "the June-year dashboard curve does not reconstruct from the dials "
            f"(worst {float(curve_drift.max()):.3e})."
        )
    june["dial_curve_year_offset"] = 0.0
    # The workbook's delta columns are in percentage POINTS. Recompute them so
    # the published comparison is verified rather than copied.
    recomputed_vfm = (
        june["mot_mbu26_official_bev_share"] - june["vfm_base_bev_share"]
    ) * 100.0
    recomputed_curve = (
        june["mot_mbu26_official_bev_share"] - june["dashboard_dial_curve_bev_share"]
    ) * 100.0
    for label, published, recomputed in (
        ("mot_minus_vfm_base_pp", june["mot_minus_vfm_base_pp"], recomputed_vfm),
        ("mot_minus_our_curve_pp", june["mot_minus_our_curve_pp"], recomputed_curve),
    ):
        drift = (published - recomputed).abs().max()
        if float(drift) > 1e-9:
            raise LegacyReconstructionError(
                f"{label}: published deltas differ from recomputed by {float(drift):.3e}."
            )
    june["recomputed_mot_minus_vfm_base_pp"] = recomputed_vfm
    june["recomputed_mot_minus_our_curve_pp"] = recomputed_curve
    june["max_abs_mot_minus_vfm_base_pp"] = june["mot_minus_vfm_base_pp"].abs().max()
    june["max_abs_mot_minus_our_curve_pp"] = june["mot_minus_our_curve_pp"].abs().max()
    return june


def lambda_allocation_summary() -> pd.DataFrame:
    """Lambda, restated from the committed investigation evidence.

    Every column here describes an ALLOCATION: one migration total M split
    between the PED stream and the Light RUC stream. No column is a weight on
    Current versus MoT, because no such weight ever existed.
    """

    waterfall = pd.read_csv(LAMBDA_EVIDENCE / "runtime_stage_waterfall.csv")
    frame = waterfall[
        [
            "june_year",
            "S0_raw_light_ruc_model_km",
            "S0_raw_ped_light_petrol_vkt_km",
            "S1_lambda_value",
            "S1_migration_total_km",
            "S1_taken_from_light_ruc_km",
            "S1_taken_from_ped_km",
            "S1_pack_conventional_km",
            "S1_pack_class_sum_km",
            "conventional_minus_raw_km",
            "class_sum_minus_raw_km",
            "universe_U_t_km",
            "mbu26_universe_km",
            "mbu26_universe_ev_phev_km",
        ]
    ].copy()

    # The arithmetic that shows lambda is an allocation: the two deductions
    # sum to the migration total exactly, and the universe gap is the reason
    # the deductions had to exist at all.
    frame["deductions_sum_km"] = (
        frame["S1_taken_from_light_ruc_km"] + frame["S1_taken_from_ped_km"]
    )
    frame["deductions_close_to_migration_total"] = (
        frame["deductions_sum_km"] - frame["S1_migration_total_km"]
    ).abs()
    frame["universe_gap_km"] = frame["mbu26_universe_km"] - frame["universe_U_t_km"]
    frame["lambda_role"] = "allocation weight between PED and Light RUC"
    frame["lambda_is_current_vs_mot_weight"] = False
    frame["workbook_validates_lambda"] = False
    frame["workbook_validates_composition_path"] = True
    frame["status"] = "retired; not restored by the anchored structural shape transition"

    # The committed investigation CSV publishes kilometres at 6 dp, so the sum
    # of two rounded deductions can differ from the rounded total by one unit
    # in the last published place. Two of the six years sit at exactly 1e-6 for
    # that reason. The tolerance is the source's precision, not a slackened
    # gate: anything larger would be a real failure of the allocation identity.
    # Tolerance = one unit in the last published place, plus the double
    # rounding error of re-adding numbers of this magnitude (~3e3 km, so a few
    # 1e-13). Two of the six years land at 1.0000003e-6: exactly one unit in
    # the last place plus that representation noise.
    source_precision = 1e-6
    magnitude = float(frame["S1_migration_total_km"].abs().max())
    tolerance = source_precision + 8.0 * np.finfo(float).eps * magnitude
    worst = float(frame["deductions_close_to_migration_total"].max())
    if worst > tolerance:
        raise LegacyReconstructionError(
            f"lambda deductions do not sum to the migration total (worst {worst:.3e}, "
            f"tolerance {tolerance:.3e}); the allocation reading of lambda is not "
            "reproducible from the evidence."
        )
    frame["deduction_closure_source_precision"] = source_precision
    frame["deduction_closure_tolerance"] = tolerance
    return frame


def defensible_vs_retired() -> pd.DataFrame:
    """The explicit split the brief asks for, with the reason for each side."""

    defensible = [
        (
            "demand_and_composition_are_separate_problems",
            "The level/growth question and the fleet-mix question are estimated and "
            "governed separately, so neither is used to patch the other.",
        ),
        (
            "vfm_as_the_fleet_transition_source",
            "VFM202405 is a purpose-built fleet-transition projection and remains the "
            "production composition source under exact Base/Fast/Slow shares.",
        ),
        (
            "official_vintage_as_an_external_structural_cross_check",
            "A published official vintage is an externally governed long-run view; "
            "using its SHAPE as a structural source is a transparent assumption.",
        ),
        (
            "transparent_base_fast_slow_composition",
            "Three named, published composition scenarios, selectable and auditable, "
            "rather than a fitted latent share.",
        ),
        (
            "explicit_s_curve_parameters",
            "Four dial parameters (speed, ceiling, midpoint, derived steepness) that "
            "a reviewer can read, change and re-fit. Verified from workbook cells.",
        ),
        (
            "preserving_an_activity_identity",
            "Classes sum to the pool and PED VKT equals VKTpc x population, so the "
            "construction cannot quietly create or destroy kilometres.",
        ),
    ]
    retired = [
        (
            "lambda_treated_as_a_behavioural_estimate",
            "Lambda was an allocation weight splitting one migration total between two "
            "streams. It was never estimated as behaviour and never weighted Current "
            "against MoT.",
        ),
        (
            "ev_inclusive_shares_applied_to_a_conventional_only_envelope",
            "MBU26 proportions describe a universe containing BEV and PHEV kilometres; "
            "they were applied to a universe built from two conventional-only streams, "
            "so the optimiser had to manufacture EV km out of them.",
        ),
        (
            "deductions_from_raw_ped_and_raw_conventional_light_ruc",
            "The migration total was subtracted from the econometric levels themselves, "
            "changing what the models estimated.",
        ),
        (
            "selection_because_it_matched_an_official_level",
            "Choosing a construction because its level lands near a published forecast "
            "is calibration to the answer, not a method.",
        ),
        (
            "shrinking_share_expansion",
            "Dividing a growing conventional forecast by a conventional share tending "
            "to zero produced the ~185,800 million km FY2050 pathology.",
        ),
    ]
    rows = [
        {
            "verdict": "DEFENSIBLE",
            "element": element,
            "reason": reason,
            "retained_in_anchored_structural_shape_transition": True,
        }
        for element, reason in defensible
    ] + [
        {
            "verdict": "RETIRED_NOT_DEFENSIBLE",
            "element": element,
            "reason": reason,
            "retained_in_anchored_structural_shape_transition": False,
        }
        for element, reason in retired
    ]
    return pd.DataFrame(rows)


def write_report(
    dials: dict[str, float],
    fits: dict[str, float],
    derived: dict[str, float],
    june: pd.DataFrame,
    lam: pd.DataFrame,
) -> None:
    fy2030 = june[june["june_year"].eq(2030)].iloc[0]
    fy2050 = june[june["june_year"].eq(2050)].iloc[0]
    lam2030 = lam[lam["june_year"].eq(2030)].iloc[0]

    text = f"""# Legacy structural method - reconstruction

Source workbook: `references/MBU26 v VFM202405_outputs_summary_V3 (1).xlsx`,
sheet `{SHEET}`. Every number below is read from a cell or recomputed from the
workbook's own series; none is taken on trust from the brief.

Regenerate with:

    .venv\\Scripts\\python.exe scripts\\build_anchored_shape_legacy_reconstruction.py

## 1. The dashboard logistic, verified from cells

The curve is an ordinary logistic in the calendar year:

    share_fy = ceiling / (1 + exp(-steepness * (fy - midpoint)))

read verbatim from `E154`:

    =$C$105/(1+EXP(-$C$106*(B154-$C$107)))

| dial | cell | value |
|---|---|---|
| Peak uptake speed (share points/year) | `C104` | {dials['peak_uptake_speed_share_points_per_year']!r} |
| Saturation ceiling | `C105` | {dials['curve_ceiling_saturation_share']!r} |
| Steepness (derived, `=4*C104/C105`) | `C106` | {dials['steepness']!r} |
| Midpoint (year of fastest uptake) | `C107` | {int(dials['midpoint_year_of_fastest_uptake'])} |

The four values in the brief are confirmed. Steepness is **derived**, not
independently set: `4 x 0.0425 / 0.920487` reproduces `C106` to 1e-12, so the
dials are mutually consistent rather than four separately typed numbers.

Rebuilding the logistic in Python from those dials reproduces the workbook's
own curve column for every year 2015-2050 to within 1e-12.

## 2. The published fit, re-derived

The workbook linearises the logistic. For `ds/dt = r*s*(1 - s/K)`,

    (ds/dt)/s = r - (r/K)*s

so regressing the mid-point growth rate (`AE`) on the mid-point share (`AD`)
over the projection era gives the steepness as the intercept and the ceiling as
the x-intercept. Recomputing that regression from the same two columns:

| statistic | workbook | recomputed | agrees |
|---|---|---|---|
| Straight-line fit R-squared | {fits['straight_line_fit_r_squared']:.16f} | {derived['recomputed_r_squared']:.16f} | yes |
| Steepness off the line | {fits['steepness_read_off_the_line']:.16f} | {derived['recomputed_steepness_intercept']:.16f} | yes |
| Ceiling off the line | {fits['ceiling_read_off_the_line']:.16f} | {derived['recomputed_ceiling_x_intercept']:.16f} | yes |

Observations: {derived['fit_observations']} (projection era 2025-2050).

The fitted values are close to but not identical with the dials - steepness
{derived['recomputed_steepness_intercept']:.6f} against a dial of
{dials['steepness']:.6f}, ceiling {derived['recomputed_ceiling_x_intercept']:.6f}
against a dial of {dials['curve_ceiling_saturation_share']:.6f}. The dials are a
rounded, human-settable version of the fit, and the workbook says so by
printing both side by side.

## 3. MBU26, VFM and the curve compared

June-year BEV share of the Light RUC pool, from the workbook's own comparison
block (rows 154-179):

| June year | MoT MBU26 | VFM Base | Dashboard curve | MoT - VFM (pp) | MoT - curve (pp) |
|---|---|---|---|---|---|
| 2030 | {fy2030['mot_mbu26_official_bev_share']:.6f} | {fy2030['vfm_base_bev_share']:.6f} | {fy2030['dashboard_dial_curve_bev_share']:.6f} | {fy2030['mot_minus_vfm_base_pp']:+.4f} | {fy2030['mot_minus_our_curve_pp']:+.4f} |
| 2050 | {fy2050['mot_mbu26_official_bev_share']:.6f} | {fy2050['vfm_base_bev_share']:.6f} | {fy2050['dashboard_dial_curve_bev_share']:.6f} | {fy2050['mot_minus_vfm_base_pp']:+.4f} | {fy2050['mot_minus_our_curve_pp']:+.4f} |

Worst absolute disagreement across FY2025-FY2050:
MoT vs VFM Base **{float(june['mot_minus_vfm_base_pp'].abs().max()):.4f} pp**;
MoT vs the dashboard curve **{float(june['mot_minus_our_curve_pp'].abs().max()):.4f} pp**.

Both published delta columns are reproduced exactly by recomputation.

The three sources agree on the *shape* of light-fleet electrification to within
about two percentage points of share across a twenty-five year horizon. That
agreement is what the workbook establishes, and it is a statement about
**composition**, not about levels or revenue.

## 4. What lambda actually was

From the committed investigation evidence
(`artifacts/fleet_allocation_semantics/`), restated in
`legacy_lambda_allocation_summary.csv`:

- **Lambda was an allocation weight.** It decided how much of a single
  migration total `M` was subtracted from the Light RUC stream and how much
  from the PED stream.
- **It split a migration total between PED and Light RUC.** At FY2030,
  lambda = {lam2030['S1_lambda_value']:.6f}, M = {lam2030['S1_migration_total_km']:.3f} million km,
  taken from Light RUC {lam2030['S1_taken_from_light_ruc_km']:.3f} and from PED
  {lam2030['S1_taken_from_ped_km']:.3f}. The two deductions sum to M exactly.
- **It was not a weight on Current versus MoT.** No such parameter existed in
  the pipeline, and the workbook contains no analogue of one.
- **The workbook validates the structural composition path, not the lambda
  coefficient.** The S-curve sheet compares BEV *shares*. Lambda appears
  nowhere in it.
- **The old implementation applied EV-inclusive proportions to an incompatible
  conventional-only envelope and therefore changed econometric levels.** The
  conserved universe was built from two conventional-only streams while the
  shares applied to it described a universe containing BEV and PHEV
  kilometres. At FY2030 that universe gap is
  {lam2030['universe_gap_km']:.3f} million km, and the optimiser had nothing to
  build EV kilometres from except the two conventional streams.

The old allocation is **not restored**. The transition weight introduced by
this branch is a different object with a different job: it is a governance
schedule moving reliance from a short-run econometric extrapolation to a
structural long-run source, it never touches a level, and it is bounded,
monotonic and exactly zero at the FY2030 anchor.

## 5. What carries forward, and what does not

See `defensible_vs_retired_method.csv`. In short: the separation of demand from
composition, VFM as the fleet-transition source, the official vintage as an
external structural cross-check, transparent Base/Fast/Slow composition,
explicit curve parameters and a preserved activity identity all carry forward.
Lambda-as-behaviour, EV-inclusive shares on a conventional-only envelope,
deductions from raw econometric streams, selection by proximity to an official
level, and shrinking-share expansion do not.
"""
    (OUT / "legacy_method_reconstruction.md").write_text(text, encoding="utf-8")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    dials, fits = read_dials()
    calendar, derived = reconstruct_s_curve(dials, fits)
    june = reconstruct_share_comparison(dials)
    lam = lambda_allocation_summary()
    split = defensible_vs_retired()

    for name, value in dials.items():
        calendar[f"dial_{name}"] = value
    calendar.to_csv(OUT / "legacy_s_curve_reconstruction.csv", index=False)
    june.to_csv(OUT / "legacy_vfm_mbu_share_comparison.csv", index=False)
    lam.to_csv(OUT / "legacy_lambda_allocation_summary.csv", index=False)
    split.to_csv(OUT / "defensible_vs_retired_method.csv", index=False)
    write_report(dials, fits, derived, june, lam)

    print("dials:", dials)
    print("published fit:", fits)
    print("recomputed fit:", derived)
    print(
        "max |MoT - VFM| pp:",
        float(june["mot_minus_vfm_base_pp"].abs().max()),
        "| max |MoT - curve| pp:",
        float(june["mot_minus_our_curve_pp"].abs().max()),
    )
    print("lambda rows:", len(lam), "| defensible/retired rows:", len(split))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

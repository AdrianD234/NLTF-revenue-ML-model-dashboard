"""Build the offline seeded draw-level uncertainty pack.

Ten thousand deterministic draws of three parent shocks, propagated through the
governed ``FORMULA_DEFINITIONS`` identities, then reduced to 50%/80% quantiles
per series and June year.

Aggregate bands are computed from AGGREGATE DRAWS. Summing marginal lower and
upper endpoints would assert a dependence structure nobody chose, and would be
wrong in both directions depending on the sign of the correlation.

Leaf treatment, by parent shock:

    PED         ped_vkt_per_capita, ped_volume, light_petrol_vkt,
                gross_ped_revenue, fed_refunds
    LIGHT_RUC   light_ruc_net_km/revenue, light_bev_*, phev_* - one factor for
                all of them, because they are one pool allocated by the
                selected exact VFM shares
    HEAVY_RUC   heavy_ruc_net_km, heavy_ruc_net_revenue
    Tier-5      heavy_bev_* (the Heavy factor, applied identically to km and
                revenue so the effective-rate identity closes),
                mr1/mr2_revenue (the MVR vintage-revision proxy),
                tuc_net_revenue (fixed: factor 1.0)

Administrative components - ruc_admin_revenue, mvr_admin_revenue, coo_revenue,
mvr_refunds, ruc_refunds, gross_lpg_revenue, gross_cng_revenue - are governed
fixed values and are held at 1.0. ``ruc_refunds`` cancels out of
``total_ruc_net_revenue`` by construction, so holding it fixed cannot bias the
RUC total.

    .venv\\Scripts\\python.exe scripts\\build_revenue_outlook_uncertainty_pack.py
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from model_dashboard.ev_uptake_levers import DEFAULT_EV_UPTAKE_MODE  # noqa: E402
from model_dashboard.mbu26_source_spine import FORMULA_DEFINITIONS  # noqa: E402
from model_dashboard.revenue_outlook import (  # noqa: E402
    CURRENT_REVENUE_OUTLOOK_DIR,
    PED_BRIDGE_DEFAULT_MODE,
    load_revenue_outlook_pack,
    revenue_outlook_signature,
)
from model_dashboard.revenue_scenario_key import RevenueScenarioComputationKey  # noqa: E402
from model_dashboard.revenue_uncertainty import (  # noqa: E402
    FINAL_FY,
    LAST_ACTUAL_FY,
    QuantileMultipliers,
    evidence_state_for_fy,
    june_year_quantiles,
)
from model_dashboard.revenue_uncertainty_draws import (  # noqa: E402
    DRAW_COUNT,
    DRAW_SEED,
    generate_parent_factor_draws,
)

LONG_HORIZON = ROOT / "artifacts" / "long_horizon_validation"
PACK_DIR = ROOT / "data" / "revenue_outlook_uncertainty"
AUDIT_DIR = ROOT / "artifacts" / "revenue_outlook_layered_uncertainty"
FORMULA_TOLERANCE = 1e-6
# Bumped to "2" when the manifest gained output_hashes and source_main_sha so
# a committed pack whose bytes differ from what its builder produced reads as
# stale in scripts/plan_governed_pack_rebuilds.py instead of silently ok.
BUILDER_VERSION = "2"


def _git_head() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()

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
# Reported series: every chartable leaf plus every governed aggregate.
FORMULA_OUTPUTS = tuple(str(d["output_series_id"]) for d in FORMULA_DEFINITIONS)
REPORTED_SERIES = tuple(dict.fromkeys((*PARENT_OF_LEAF.keys(), *FORMULA_OUTPUTS)))


def production_key(pack) -> RevenueScenarioComputationKey:
    block = pack.manifest.get("official_vintages", {}) if isinstance(pack.manifest, dict) else {}
    return RevenueScenarioComputationKey(
        uptake_basis=DEFAULT_EV_UPTAKE_MODE,
        current_fed_policy_state=app.FED_POLICY_DELAYED_6M,
        official_fed_policy_state=app.FED_POLICY_PUBLISHED,
        official_comparator_vintage_id=str(block.get("default_comparator_vintage_id") or "BEFU26"),
        long_run_transition_schedule_id=str(
            block.get("long_run_transition_schedule_id") or app.UNBLENDED_SCHEDULE_ID
        ),
        long_run_shape_vintage_id=str(block.get("long_run_shape_vintage_id") or ""),
    )


def central_leaf_values(pack, signature, key) -> dict[tuple[str, int], float]:
    """Governed central values per (series, FY) for the Current base case."""
    line, _residuals, _stack, _bridge = app.cached_aligned_scenario_detail_frames(
        signature,
        app.selected_sensitivity_key("Off", "Off", "Off", freight_rail_shift="Off"),
        PED_BRIDGE_DEFAULT_MODE,
        key,
        pack,
    )
    selected = line[line["scenario_name"].astype(str).eq("current_basecase")].copy()
    selected["FY"] = pd.to_numeric(selected["FY"], errors="coerce")
    selected["value"] = pd.to_numeric(selected["value"], errors="coerce")
    selected = selected.dropna(subset=["FY", "value"])
    out: dict[tuple[str, int], float] = {}
    for _index, row in selected.iterrows():
        out.setdefault((str(row["series_id"]), int(row["FY"])), float(row["value"]))
    return out


def mvr_proxy() -> QuantileMultipliers:
    """The committed BEFU26-vs-MBU26 revision range. Never called empirical."""
    pack = load_revenue_outlook_pack(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, repo_root=ROOT)
    frame = pack.revenue_line_reconciliation.copy()
    frame["FY"] = pd.to_numeric(frame["FY"], errors="coerce")
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    selected = frame[
        frame["series_id"].astype(str).eq("net_mvr_revenue")
        & frame["FY"].between(LAST_ACTUAL_FY + 1, FINAL_FY)
    ]
    pivot = selected.pivot_table(index="FY", columns="source_path", values="value", aggfunc="first")
    half = 0.02
    if "BEFU26 official" in pivot and "MBU26 official" in pivot:
        revision = np.log(pivot["MBU26 official"] / pivot["BEFU26 official"]).dropna()
        if len(revision):
            half = float(revision.abs().max())
    # The inner 50% proxy is HALF the observed outer range. The source has no
    # usable inner quantile (24 of 25 years agree exactly), so the inner band is
    # derived by construction, not measured - stated plainly in the contract.
    return QuantileMultipliers(q10=-half, q25=-half / 2.0, median=0.0, q75=half / 2.0, q90=half)


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


def main() -> None:
    PACK_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    june_errors = pd.read_csv(LONG_HORIZON / "long_horizon_june_year_errors.csv")
    quantiles = june_year_quantiles(june_errors)
    parent_draws, provenance = generate_parent_factor_draws(june_errors, quantiles)

    pack = load_revenue_outlook_pack(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, repo_root=ROOT)
    signature = revenue_outlook_signature(ROOT / CURRENT_REVENUE_OUTLOOK_DIR, ROOT)
    key = production_key(pack)
    central = central_leaf_values(pack, signature, key)
    mvr_multipliers = mvr_proxy()

    band_rows: list[dict] = []
    residual_rows: list[dict] = []
    contribution_rows: list[dict] = []

    for fy in range(LAST_ACTUAL_FY + 1, FINAL_FY + 1):
        factors = parent_draws.get(fy)
        if not factors:
            continue
        mvr_factor = np.exp(
            np.sort(
                np.quantile(
                    np.array([mvr_multipliers.q10, mvr_multipliers.q25, mvr_multipliers.median,
                              mvr_multipliers.q75, mvr_multipliers.q90]),
                    np.linspace(0.0, 1.0, DRAW_COUNT),
                )
            )
        )
        # Give the MVR proxy its own independent ordering: it is a vintage
        # revision, not a model error, and has no measured relationship to the
        # three forecast streams.
        mvr_shuffle = np.random.default_rng(DRAW_SEED + 1).permutation(DRAW_COUNT)
        mvr_factor = mvr_factor[mvr_shuffle]

        leaf_draws: dict[str, np.ndarray] = {}
        for leaf, parent in PARENT_OF_LEAF.items():
            value = central.get((leaf, fy))
            if value is None:
                continue
            if parent == "FIXED":
                factor = np.ones(DRAW_COUNT)
            elif parent == "MVR_PROXY":
                factor = mvr_factor
            elif parent == "HEAVY_RUC_PROXY":
                factor = factors["HEAVY_RUC"]
            else:
                factor = factors[parent]
            leaf_draws[leaf] = value * factor

        evaluated = evaluate_formulas(leaf_draws, DRAW_COUNT)

        # ---- identity closure, on EVERY draw, not just at the percentiles
        for definition in FORMULA_DEFINITIONS:
            output = str(definition["output_series_id"])
            if output not in evaluated:
                continue
            recomputed = np.zeros(DRAW_COUNT)
            complete = True
            for term, sign in definition["terms"]:
                if str(term) not in evaluated:
                    complete = False
                    break
                recomputed = recomputed + float(sign) * evaluated[str(term)]
            if not complete:
                continue
            worst = float(np.max(np.abs(recomputed - evaluated[output])))
            residual_rows.append(
                {
                    "FY": fy,
                    "output_series_id": output,
                    "expression": definition["expression"],
                    "draws_checked": DRAW_COUNT,
                    "max_abs_residual": worst,
                    "closes": bool(worst <= FORMULA_TOLERANCE),
                }
            )

        # ---- band rows
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
                    "scenario_key_digest": key.cache_token(),
                    "engine": "ensemble",
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
                    "method": "conditional model forecast-error band (actual-driver rolling origin)",
                }
            )

        # ---- Tier-5 contribution to the Total NLTF band
        if "total_nltf_net_revenue" in evaluated:
            full = evaluated["total_nltf_net_revenue"]
            full_span = float(np.quantile(full, 0.90) - np.quantile(full, 0.10))
            for label, muted in (
                ("heavy_bev_proxy", HEAVY_BEV_PROXY_LEAVES),
                ("mvr_proxy", MVR_PROXY_LEAVES),
                ("tuc_fixed", ("tuc_net_revenue",)),
            ):
                muted_draws = dict(leaf_draws)
                for leaf in muted:
                    value = central.get((leaf, fy))
                    if value is not None:
                        muted_draws[leaf] = np.full(DRAW_COUNT, value)
                muted_eval = evaluate_formulas(muted_draws, DRAW_COUNT)
                muted_total = muted_eval["total_nltf_net_revenue"]
                muted_span = float(np.quantile(muted_total, 0.90) - np.quantile(muted_total, 0.10))
                contribution_rows.append(
                    {
                        "FY": fy,
                        "tier5_component": label,
                        "total_span80_with": full_span,
                        "total_span80_without": muted_span,
                        "contribution_pct_of_span": (
                            100.0 * (full_span - muted_span) / full_span if full_span else 0.0
                        ),
                    }
                )

    bands = pd.DataFrame(band_rows)
    bands.to_parquet(PACK_DIR / "uncertainty_band_rows.parquet", index=False)
    bands.to_csv(AUDIT_DIR / "uncertainty_band_values.csv", index=False)

    residuals = pd.DataFrame(residual_rows)
    residuals.to_csv(AUDIT_DIR / "draw_level_formula_residuals.csv", index=False)

    contributions = pd.DataFrame(contribution_rows)
    contributions.to_csv(AUDIT_DIR / "tier5_contribution_audit.csv", index=False)

    quantiles.to_parquet(PACK_DIR / "june_year_basis.parquet", index=False)
    manifest = {
        **provenance,
        "scenario_key": key.canonical_mapping(),
        "scenario_key_digest": key.digest(),
        "formula_tolerance": FORMULA_TOLERANCE,
        "series_count": int(bands["series_id"].nunique()),
        "fy_range": [int(bands["FY"].min()), int(bands["FY"].max())],
        "band_rows": int(len(bands)),
        "source_files": {
            "june_year_errors": "artifacts/long_horizon_validation/long_horizon_june_year_errors.csv",
            "central_path": "data/current_revenue_outlook (line reconciliation, current_basecase)",
        },
        # Content pinning: lets the planner detect a committed pack whose
        # bytes are not the ones this builder produced. Freshness (whether the
        # inputs moved) remains the policy runtime's digest chain.
        "builder_version": BUILDER_VERSION,
        "source_main_sha": _git_head(),
        "output_hashes": {
            name: _sha256_file(PACK_DIR / name)
            for name in ("uncertainty_band_rows.parquet", "june_year_basis.parquet")
        },
    }
    (PACK_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # ------------------------------------------------------------- reporting
    print(f"band rows: {len(bands)}   series: {bands['series_id'].nunique()}   "
          f"FY {bands['FY'].min()}-{bands['FY'].max()}")
    failures = residuals[~residuals["closes"]]
    print(f"\nformula identities checked on every draw: {len(residuals)} (series x FY)")
    print(f"  failures above {FORMULA_TOLERANCE}: {len(failures)}")
    if not failures.empty:
        print(failures.nlargest(5, "max_abs_residual").to_string(index=False))
        raise SystemExit(1)
    print(f"  worst residual seen: {residuals['max_abs_residual'].max():.3e}")

    print("\n=== 80% span (%) at selected FYs ===")
    view = bands[bands["FY"].isin((2027, 2030, 2031, 2040, 2050))]
    print(
        view.pivot_table(index="series_id", columns="FY", values="span80_pct")
        .round(2).to_string()
    )
    print("\n=== Tier-5 contribution to the Total NLTF 80% span ===")
    print(
        contributions[contributions["FY"].isin((2030, 2050))]
        .pivot_table(index="tier5_component", columns="FY", values="contribution_pct_of_span")
        .round(3).to_string()
    )
    print(f"\nwrote {PACK_DIR}")


if __name__ == "__main__":
    main()

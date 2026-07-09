"""Uptake shape lab: is the S-curve in the data, or imposed by our formula?

Four independent lines of evidence, each computed from source data with no
role for our preset coefficients:

1. FUNCTIONAL-FORM TOURNAMENT - fit many candidate shapes (linear, quadratic,
   cubic, exponential, power, logistic, Gompertz, Richards, Bass diffusion)
   to the VFM share series, then score them on a HELD-OUT TAIL: fit on
   2024-2040 only and predict 2041-2050. A flexible form can mimic anything
   in-sample; only a form whose shape matches the data's structure survives
   extrapolation.

2. GROWTH-RATE SIGNATURE (no fitting) - for a saturating adoption process,
   the year-on-year relative growth rate ds/dt / s falls LINEARLY as the
   share s rises:  s'/s = k (1 - s/smax).  Regressing growth rate on share
   is a structural test: linearity is falsifiable, the x-intercept IS the
   saturation ceiling and the intercept IS the speed constant - both read
   off VFM's own series rather than chosen by us.

3. STOCK-FLOW MECHANISM (inside VFM) - VFM is a fleet-turnover model. Using
   only VFM's own new-vehicle sales mix and its own fleet turnover rate,
   integrate  fleet(t+1) = fleet(t) + turnover x (new-sales share - fleet(t))
   and compare with VFM's actual fleet share. If the reconstruction tracks,
   the S-curve is fleet arithmetic, not a fitted coefficient.

4. OBSERVED NEW ZEALAND HISTORY (outside VFM) - the MBU26 spine's actual
   light BEV shares (real outturns to FY2025). Do the observed points sit on
   the same growth-rate line VFM projects?

Writes artifacts/uptake_shape_lab/ (CSVs + report.md).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "artifacts" / "uptake_shape_lab"
WORKBOOK = ROOT / "data" / "source_workbooks" / "VFM202405_outputs_summary_V3.xlsx"
SPLIT_AUDIT = ROOT / "data" / "current_revenue_outlook" / "ev_phev_split_assumptions.csv"

SCENARIOS = ("Base_EV", "Fast_EV", "Slow_EV")
LIGHT = ("LPV", "LCV")
CONVENTIONAL = ("Diesel", "Hybrid diesel")
POOL_POWER = (*CONVENTIONAL, "Electric", "Petrol plug-in")
FIT_END = 2040             # training window ends here (history included)
HOLDOUT_YEARS = (2041, 2050)


# ------------------------------------------------------------------ data ----
def load_vfm_raw() -> pd.DataFrame:
    raw = pd.read_excel(WORKBOOK, sheet_name="Raw data (wem202405)", skiprows=2, header=None)
    raw.columns = ["scenario", "light_heavy", "electric", "veh_type", "power_type", "new_used",
                   "veh_size", "year", "vehicles", "vkt", "fuel_use", "kwh_use",
                   "fuel_co2", "electricity_co2"][: raw.shape[1]]
    raw["year"] = pd.to_numeric(raw["year"], errors="coerce")
    raw["vkt"] = pd.to_numeric(raw["vkt"], errors="coerce")
    raw["vehicles"] = pd.to_numeric(raw["vehicles"], errors="coerce")
    raw = raw.dropna(subset=["year"])
    raw["year"] = raw["year"].astype(int)
    return raw


def load_vfm_registrations() -> pd.DataFrame:
    regs = pd.read_excel(WORKBOOK, sheet_name="Registrations", skiprows=2, header=None)
    regs.columns = ["scenario", "electric", "veh_type", "power_type", "new_used",
                    "veh_size", "year", "registration"][: regs.shape[1]]
    regs["year"] = pd.to_numeric(regs["year"], errors="coerce")
    regs["registration"] = pd.to_numeric(regs["registration"], errors="coerce")
    regs = regs.dropna(subset=["year"])
    regs["year"] = regs["year"].astype(int)
    return regs


def light_pool_series(raw: pd.DataFrame, regs: pd.DataFrame, scenario: str) -> pd.DataFrame:
    """Per calendar year: light RUC pool VKT shares, vehicle stocks and
    registration flows (both import channels, N + U)."""
    lp = raw[(raw["scenario"] == scenario) & (raw["veh_type"].isin(LIGHT))]
    lr = regs[(regs["scenario"] == scenario) & (regs["veh_type"].isin(LIGHT))]

    def vkt_by(power: tuple[str, ...]) -> pd.Series:
        return lp[lp["power_type"].isin(power)].groupby("year")["vkt"].sum()

    def vehicles_by(power: tuple[str, ...]) -> pd.Series:
        return lp[lp["power_type"].isin(power)].groupby("year")["vehicles"].sum()

    def regos_by(power: tuple[str, ...]) -> pd.Series:
        return lr[lr["power_type"].isin(power)].groupby("year")["registration"].sum()

    out = pd.DataFrame({
        "bev_vkt": vkt_by(("Electric",)),
        "phev_vkt": vkt_by(("Petrol plug-in",)),
        "conv_vkt": vkt_by(CONVENTIONAL),
        "bev_stock": vehicles_by(("Electric",)),
        "pool_stock": vehicles_by(POOL_POWER),
        "bev_regs": regos_by(("Electric",)),
        "pool_regs": regos_by(POOL_POWER),
    }).fillna(0.0)
    out["pool_vkt"] = out["bev_vkt"] + out["phev_vkt"] + out["conv_vkt"]
    out["bev_share_vkt"] = out["bev_vkt"] / out["pool_vkt"]
    out["bev_share_stock"] = out["bev_stock"] / out["pool_stock"]
    with np.errstate(divide="ignore", invalid="ignore"):
        out["new_entry_bev_share"] = np.where(out["pool_regs"] > 0, out["bev_regs"] / out["pool_regs"], np.nan)
        out["turnover"] = np.where(out["pool_stock"] > 0, out["pool_regs"] / out["pool_stock"], np.nan)
    return out


# ------------------------------------------------- 1. form tournament -------
def candidate_forms():
    """name -> (n_params, initial guess fn, model fn). t is years since 2024."""
    def logistic(t, smax, k, t0):
        return smax / (1 + np.exp(-np.clip(k * (t - t0), -50, 50)))

    def gompertz(t, smax, b, c):
        return smax * np.exp(-b * np.exp(-np.clip(c, 1e-6, None) * t))

    def richards(t, smax, k, t0, nu):
        nu = np.clip(nu, 0.05, 20)
        return smax / (1 + nu * np.exp(-np.clip(k * (t - t0), -50, 50))) ** (1 / nu)

    def bass(t, m, p, q):
        p = np.clip(p, 1e-5, 1.0)
        q = np.clip(q, 1e-5, 3.0)
        e = np.exp(-np.clip((p + q) * t, -50, 50))
        return m * (1 - e) / (1 + (q / p) * e)

    return {
        "linear": (2, lambda y: [y[0], (y[-1] - y[0]) / 26], lambda t, a, b: a + b * t),
        "quadratic": (3, lambda y: [y[0], 0.01, 0.0], lambda t, a, b, c: a + b * t + c * t**2),
        "cubic": (4, lambda y: [y[0], 0.01, 0.0, 0.0], lambda t, a, b, c, d2: a + b * t + c * t**2 + d2 * t**3),
        "exponential": (2, lambda y: [max(y[0], 1e-3), 0.1], lambda t, a, b: a * np.exp(np.clip(b * t, -50, 50))),
        "power": (2, lambda y: [max(y[0], 1e-3), 1.0], lambda t, a, b: a * np.power(np.maximum(t, 1e-9), b)),
        "logistic (S-curve)": (3, lambda y: [min(1.0, y[-1] * 1.2), 0.25, 12.0], logistic),
        "Gompertz (S-curve)": (3, lambda y: [min(1.0, y[-1] * 1.2), 3.0, 0.15], gompertz),
        "Richards (S-curve)": (4, lambda y: [min(1.0, y[-1] * 1.2), 0.25, 12.0, 1.0], richards),
        "Bass diffusion (S-curve)": (3, lambda y: [min(1.0, y[-1] * 1.2), 0.01, 0.4], bass),
    }


def run_tournament(series: pd.Series) -> pd.DataFrame:
    from scipy.optimize import curve_fit

    years = series.index.to_numpy(dtype=float)
    t = years - 2024.0
    y = series.to_numpy(dtype=float)
    fit_mask = years <= FIT_END          # full history through 2040
    hold_mask = (years >= HOLDOUT_YEARS[0]) & (years <= HOLDOUT_YEARS[1])
    rows = []
    for name, (n_params, guess, fn) in candidate_forms().items():
        try:
            popt, _ = curve_fit(fn, t[fit_mask], y[fit_mask], p0=guess(y[fit_mask]), maxfev=40000)
            fit_pred = fn(t[fit_mask], *popt)
            hold_pred = fn(t[hold_mask], *popt)
            rmse_fit = float(np.sqrt(np.mean((fit_pred - y[fit_mask]) ** 2)))
            rmse_hold = float(np.sqrt(np.mean((hold_pred - y[hold_mask]) ** 2)))
            n = int(fit_mask.sum())
            aicc = n * np.log(max(rmse_fit, 1e-12) ** 2) + 2 * n_params * n / max(n - n_params - 1, 1)
            rows.append(dict(form=name, params=n_params, rmse_fit_pp=rmse_fit * 100,
                             rmse_holdout_pp=rmse_hold * 100, aicc=aicc,
                             pred_2050_pp=float(fn(np.array([2050.0 - 2024.0]), *popt)[0]) * 100))
        except Exception as exc:  # noqa: BLE001 - a form failing to converge is a result
            rows.append(dict(form=name, params=n_params, rmse_fit_pp=np.nan,
                             rmse_holdout_pp=np.nan, aicc=np.nan, pred_2050_pp=np.nan,
                             note=f"fit failed: {exc}"))
    return pd.DataFrame(rows).sort_values("rmse_holdout_pp")


# ----------------------------------------- 2. growth-rate signature ---------
def growth_rate_regression(series: pd.Series, min_year: float | None = None) -> dict:
    """Regress relative growth rate on share: s'/s = k (1 - s/smax)."""
    s = series.to_numpy(dtype=float)
    years = series.index.to_numpy(dtype=float)
    mid_share = (s[1:] + s[:-1]) / 2
    mid_year = (years[1:] + years[:-1]) / 2
    with np.errstate(divide="ignore", invalid="ignore"):
        growth = np.diff(s) / np.diff(years) / mid_share
    keep = (mid_share > 0.005) & np.isfinite(growth)
    if min_year is not None:
        keep &= mid_year >= min_year
    x, g = mid_share[keep], growth[keep]
    if keep.sum() < 4:
        return dict(k=float("nan"), smax=float("nan"), r2=float("nan"),
                    n_points=int(keep.sum()), points=pd.DataFrame({"share": x, "relative_growth": g}))
    slope, intercept = np.polyfit(x, g, 1)
    r2 = float(np.corrcoef(x, g)[0, 1] ** 2)
    return dict(k=float(intercept), smax=float(-intercept / slope), r2=r2,
                n_points=int(keep.sum()),
                points=pd.DataFrame({"share": x, "relative_growth": g}))


# ----------------------------------------- 3. stock-flow reconstruction -----
def stock_flow_reconstruction(pool: pd.DataFrame) -> pd.DataFrame:
    """fleet(t+1) = fleet(t) + turnover(t) x (new-entry share(t) - fleet(t)).

    Neutral-scrappage recursion: retirements are assumed to carry the fleet-
    average mix. In reality retirements skew towards older conventional
    vehicles, so this reconstruction should slightly UNDERSHOOT the true BEV
    share - the sign of any gap is itself a check on the mechanism.
    """
    flows = pool[pool["new_entry_bev_share"].notna() & (pool["turnover"] > 0)]
    years = flows.index.to_numpy()
    rec = np.zeros(len(years))
    rec[0] = flows["bev_share_stock"].iloc[0]  # single seed: VFM's first flow-era share
    for i in range(len(years) - 1):
        turn = float(flows["turnover"].iloc[i])
        flow = float(flows["new_entry_bev_share"].iloc[i])
        rec[i + 1] = rec[i] + turn * (flow - rec[i])
    return pd.DataFrame({
        "year": years,
        "new_entry_bev_share": flows["new_entry_bev_share"].to_numpy(),
        "turnover": flows["turnover"].to_numpy(),
        "vfm_fleet_bev_share_stock": flows["bev_share_stock"].to_numpy(),
        "reconstructed_fleet_share": rec,
        "vfm_bev_share_vkt": flows["bev_share_vkt"].to_numpy(),
    })


# ----------------------------------------- 4. observed NZ history -----------
def observed_nz_history() -> pd.Series:
    split = pd.read_csv(SPLIT_AUDIT)
    actual = split[split["source_status"] == "ACTUAL"]
    share = actual.drop_duplicates("FY").set_index("FY")["light_bev_share"].astype(float)
    # MBU26 only splits the light BEV class out from ~FY2024; earlier zeros are
    # a reporting-granularity artifact, not observed zeros.
    return share[share > 0]


# ------------------------------------------------------------------ main ----
def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    raw = load_vfm_raw()
    regs = load_vfm_registrations()
    pools = {scen: light_pool_series(raw, regs, scen) for scen in SCENARIOS}

    report = ["# Uptake shape lab - is the S-curve in the data?", ""]

    # 1. tournament on the primary curve (light BEV VKT share) per scenario
    for scen in SCENARIOS:
        t = run_tournament(pools[scen]["bev_share_vkt"])
        t.to_csv(OUT / f"tournament_light_bev_{scen}.csv", index=False)
        if scen == "Base_EV":
            base_t = t
    years = pools["Base_EV"].index
    report += ["## 1. Functional-form tournament (light BEV share of the light RUC pool)",
               "", f"Fit on {int(years.min())}-{FIT_END} (history included), judged on held-out "
               f"{HOLDOUT_YEARS[0]}-{HOLDOUT_YEARS[1]}.",
               "", "Base scenario (percentage points):", "",
               base_t.to_string(index=False), ""]

    # 2. growth-rate signature per scenario + preset cross-check
    from model_dashboard.ev_uptake_levers import EV_UPTAKE_PRESETS, solve_logistic_from_levers

    report += ["## 2. Growth-rate signature (no curve fitting)", "",
               "s'/s regressed on s: linear decline is the structural signature of saturating",
               "adoption; the x-intercept is the ceiling, the intercept the speed constant.",
               "'proj' restricts to the projection era (2024+); 'all' includes the policy-era history.", ""]
    grr_rows = []
    for scen, preset_name in [("Base_EV", "MoT VFM base"), ("Fast_EV", "MoT VFM fast"), ("Slow_EV", "MoT VFM slow")]:
        series = pools[scen]["bev_share_vkt"]
        g_all = growth_rate_regression(series)
        g_proj = growth_rate_regression(series, min_year=2024)
        g_proj["points"].assign(scenario=scen).to_csv(OUT / f"growth_rate_points_{scen}.csv", index=False)
        p = EV_UPTAKE_PRESETS[preset_name]
        smax_preset, k_preset = solve_logistic_from_levers(p.bev_peak_speed_pp, p.bev_peak_year, p.bev_share_2050)
        grr_rows.append(dict(scenario=scen,
                             r2_all=round(g_all["r2"], 3), r2_proj=round(g_proj["r2"], 3), n_proj=g_proj["n_points"],
                             ceiling_measured=round(g_proj["smax"], 3), ceiling_preset=round(smax_preset, 3),
                             speed_measured=round(g_proj["k"], 3), speed_preset=round(k_preset, 3)))
    grr = pd.DataFrame(grr_rows)
    grr.to_csv(OUT / "growth_rate_regression.csv", index=False)
    report += [grr.to_string(index=False), ""]

    # 3. stock-flow reconstruction per scenario (real registration flows)
    report += ["## 3. Stock-flow mechanism (VFM's own arithmetic)", "",
               "fleet(t+1) = fleet(t) + turnover(t) x (new-entry share(t) - fleet(t)),",
               "with turnover = light registrations / light stock, both from the VFM workbook.", ""]
    for scen in SCENARIOS:
        rec = stock_flow_reconstruction(pools[scen])
        rec.to_csv(OUT / f"stock_flow_{scen}.csv", index=False)
        err = float(np.abs(rec["reconstructed_fleet_share"] - rec["vfm_fleet_bev_share_stock"]).max()) * 100
        bias = float((rec["reconstructed_fleet_share"] - rec["vfm_fleet_bev_share_stock"]).mean()) * 100
        report += [f"- {scen}: max |reconstruction - VFM fleet share| = {err:.2f} pp, mean bias {bias:+.2f} pp "
                   f"(mean turnover {rec['turnover'].mean() * 100:.1f}%/yr)"]
    report += [""]

    # 4. observed NZ history against the VFM curve
    obs = observed_nz_history()
    obs.to_csv(OUT / "observed_nz_bev_share.csv")
    base = pools["Base_EV"]["bev_share_vkt"]
    # compare observed FY shares with VFM (June-year approx: mean of adjacent calendar years)
    overlay = []
    for fy, val in obs.items():
        if fy - 1 in base.index and fy in base.index:
            vfm_fy = (base.loc[fy - 1] + base.loc[fy]) / 2
            overlay.append(dict(FY=int(fy), observed_pct=val * 100, vfm_base_pct=float(vfm_fy) * 100,
                                gap_pp=(val - float(vfm_fy)) * 100))
    overlay_df = pd.DataFrame(overlay)
    overlay_df.to_csv(OUT / "observed_vs_vfm.csv", index=False)
    report += ["## 4. Observed New Zealand history (outside VFM)", "",
               f"MBU26 actual light BEV share: FY{int(obs.index.min())}-FY{int(obs.index.max())}, "
               f"ending at {obs.iloc[-1] * 100:.2f}%.", ""]
    if not overlay_df.empty:
        report += [overlay_df.tail(6).to_string(index=False), ""]

    (OUT / "report.md").write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))


if __name__ == "__main__":
    main()

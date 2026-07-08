"""Mint the AR(1)-engine evidence pack under data/engine_ar1/dashboard_evidence_pack/.

Copies the incumbent evidence pack and replaces the PED finalist surfaces with
the AR(1) engine (`PED__DIAGLAB__B__glsar__ylag1__ar1__wexp`):

- prediction-level tables are template-merged: the incumbent PED finalist rows
  keep their exact (score_basis, origin, target_period) keys and schema, with
  predictions/errors recomputed from the AR(1) backtest;
- summary tables (finalists, horizon/stress profiles, annual pairs, paired vs
  Schiff, scenario comparison) are recomputed with the same governed formulas
  (pipeline/vnext_core scoring helpers);
- the diagnostics battery (pipeline/diaglab_battery, verified to reproduce
  governance to float precision) rebuilds diagnostic_tests /
  diagnostic_test_detail / diagnostic_pass_matrix / diagnostic_acf for PED;
- registry/coefficients/ensemble/importance describe the single linear
  component; SHAP and scenario-sensitivity PED rows are dropped (linear
  engine - coefficients are the interpretability surface).

Light RUC and Heavy RUC rows are byte-identical to the incumbent pack.
Deterministic; the incumbent pack is never modified.

Usage: python scripts/build_ar1_evidence_pack.py
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from pipeline import vnext_core as vc  # noqa: E402
from pipeline.ar1_engine import AR1_MODEL_NAME, load_state  # noqa: E402
from pipeline.diaglab_battery import run_battery  # noqa: E402

SRC = REPO_ROOT / "data" / "dashboard_evidence_pack"
DST = REPO_ROOT / "data" / "engine_ar1" / "dashboard_evidence_pack"
WINNER_PREDICTIONS = (
    REPO_ROOT / "artifacts" / "diagnostics_lab" / "ped" / "winners" / f"{AR1_MODEL_NAME}.predictions.parquet"
)
INCUMBENT_PED = "PED__VNEXT_SOLVED_CONVEX_TOP2"
MODEL_SHORT = "AR(1) model"
SOURCE_DATASET = "diagnostics_lab/ar1_engine"
AR1_CANDIDATE_UID = "PED_AR1_GLSAR_0001"


def _read(name: str) -> pd.DataFrame:
    return pd.read_parquet(DST / "data" / f"{name}.parquet")


def _write(name: str, frame: pd.DataFrame) -> None:
    frame.to_parquet(DST / "data" / f"{name}.parquet", index=False)


def _is_ped_finalist(frame: pd.DataFrame) -> pd.Series:
    return frame["stream"].astype(str).eq("PED") & frame["model"].astype(str).eq(INCUMBENT_PED)


def _override_model_columns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["model"] = AR1_MODEL_NAME
    if "model_short" in out.columns:
        out["model_short"] = MODEL_SHORT
    if "source_dataset" in out.columns:
        out["source_dataset"] = SOURCE_DATASET
    return out


def _merge_predictions(template: pd.DataFrame, preds: pd.DataFrame) -> pd.DataFrame:
    """Template rows keep their keys/schema; pred + error fields come from AR1."""
    out = _override_model_columns(template)
    merged = out.merge(
        preds[["origin", "target_period", "pred"]].rename(columns={"pred": "_ar1_pred"}),
        on=["origin", "target_period"],
        how="left",
    )
    if merged["_ar1_pred"].isna().any():
        missing = merged[merged["_ar1_pred"].isna()][["origin", "target_period"]].head()
        raise SystemExit(f"AR1 predictions missing for template keys, e.g.\n{missing}")
    merged["pred"] = merged.pop("_ar1_pred")
    actual = pd.to_numeric(merged["actual"], errors="coerce")
    merged["error_pct"] = 100.0 * (merged["pred"] - actual) / actual
    merged["abs_error_pct"] = merged["error_pct"].abs()
    if "ape" in merged.columns:
        merged["ape"] = merged["abs_error_pct"]
    return merged


def _grid_frames(scorecard: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {str(basis): g.copy() for basis, g in scorecard.groupby("score_basis")}


def main() -> int:
    if DST.exists():
        shutil.rmtree(DST)
    shutil.copytree(SRC, DST)

    winner = pd.read_parquet(WINNER_PREDICTIONS)
    winner = winner[["origin", "target_period", "horizon", "actual", "pred"]].copy()
    state = load_state(REPO_ROOT)
    if state is None:
        raise SystemExit("ped_ar1 fitted state missing; run scripts/build_ar1_engine_state.py")

    # ---- scorecard_predictions (the master keyed table) -------------------
    scorecard = _read("scorecard_predictions")
    ped_mask = _is_ped_finalist(scorecard)
    template = scorecard[ped_mask].copy()
    replaced = _merge_predictions(template, winner)
    scorecard = pd.concat([scorecard[~ped_mask], replaced], ignore_index=True)
    _write("scorecard_predictions", scorecard)
    ar1_rows = replaced
    grids = _grid_frames(ar1_rows)
    paper = grids[vc.PAPER_SCORE_BASIS]
    operational = grids[vc.OPERATIONAL_SCORE_BASIS]

    # ---- residual_predictions / error_distribution (paper grid) ----------
    for name in ("residual_predictions", "error_distribution"):
        frame = _read(name)
        mask = _is_ped_finalist(frame)
        frame = pd.concat([frame[~mask], _merge_predictions(frame[mask].copy(), winner)], ignore_index=True)
        _write(name, frame)

    # ---- annual_predictions ----------------------------------------------
    annual = _read("annual_predictions")
    mask = _is_ped_finalist(annual)
    ann_template = _override_model_columns(annual[mask].copy())
    sums = (
        ar1_rows.assign(target_year=ar1_rows["target_period"].astype(str).str.slice(0, 4).astype(int))
        .groupby(["score_basis", "origin", "target_year"], as_index=False)
        .agg(actual_sum=("actual", "sum"), pred_sum=("pred", "sum"), n_quarters=("pred", "size"))
    )
    ann = ann_template.merge(
        sums.rename(columns={"pred_sum": "_pred", "actual_sum": "_actual", "n_quarters": "_n"}),
        on=["score_basis", "origin", "target_year"],
        how="left",
    )
    ann["pred"] = ann.pop("_pred")
    ann["actual"] = np.where(ann["_actual"].notna(), ann["_actual"], ann["actual"])
    ann = ann.drop(columns=["_actual"])
    ann["n_quarters"] = np.where(ann["_n"].notna(), ann["_n"], ann["n_quarters"])
    ann = ann.drop(columns=["_n"])
    actual = pd.to_numeric(ann["actual"], errors="coerce")
    ann["error_pct"] = 100.0 * (ann["pred"] - actual) / actual
    ann["ape"] = ann["error_pct"].abs()
    annual = pd.concat([annual[~mask], ann], ignore_index=True)
    _write("annual_predictions", annual)

    # ---- horizon profiles + stress buckets --------------------------------
    def _replace_horizon_profiles(name: str) -> None:
        frame = _read(name)
        mask = _is_ped_finalist(frame)
        tmpl = _override_model_columns(frame[mask].copy())
        rows = []
        for _, row in tmpl.iterrows():
            basis = str(row["score_basis"])
            g = grids.get(basis, pd.DataFrame())
            sub = g[g["horizon"].eq(int(row["horizon"]))]
            a = pd.to_numeric(sub["actual"], errors="coerce").to_numpy(float)
            p = pd.to_numeric(sub["pred"], errors="coerce").to_numpy(float)
            new = row.copy()
            new["mape"] = vc.mape(a, p)
            new["bias_pct"] = vc.bias_pct(a, p)
            new["n"] = int(len(sub))
            rows.append(new)
        frame = pd.concat([frame[~mask], pd.DataFrame(rows)], ignore_index=True)
        _write(name, frame)

    def _replace_stress(name: str) -> None:
        frame = _read(name)
        mask = _is_ped_finalist(frame)
        tmpl = _override_model_columns(frame[mask].copy())
        rows = []
        for _, row in tmpl.iterrows():
            basis = str(row["score_basis"])
            g = grids.get(basis, pd.DataFrame())
            buckets = vc.stress_buckets(g.rename(columns={}), basis, "PED")
            match = buckets[buckets["stress_bucket"].astype(str).eq(str(row["stress_bucket"]))]
            new = row.copy()
            if not match.empty:
                new["mape"] = float(match["mape"].iloc[0])
                new["bias_pct"] = float(match["bias_pct"].iloc[0])
                new["n"] = int(match["n"].iloc[0])
            rows.append(new)
        frame = pd.concat([frame[~mask], pd.DataFrame(rows)], ignore_index=True)
        _write(name, frame)

    _replace_horizon_profiles("horizon_profiles")
    _replace_horizon_profiles("scorecard_horizon_profiles")
    _replace_stress("stress_horizon")
    _replace_stress("scorecard_stress_horizon")

    # ---- finalists ---------------------------------------------------------
    finalists = _read("finalists")
    fmask = finalists["stream"].astype(str).eq("PED")
    frow = finalists[fmask].iloc[0].copy()
    paper_score = vc.score_frame(paper, vc.PAPER_SCORE_BASIS)
    oper_score = vc.score_frame(operational, vc.OPERATIONAL_SCORE_BASIS)
    frow["model"] = AR1_MODEL_NAME
    frow["model_short"] = MODEL_SHORT
    frow["candidate_uid"] = AR1_CANDIDATE_UID
    frow["ensemble_components_json"] = json.dumps(
        [{"component_model": AR1_MODEL_NAME, "component_label": "AR1", "weight": 1.0}]
    )
    frow["n_quarterly_pairs"] = paper_score["n_quarterly_pairs"]
    frow["quarterly_mape"] = paper_score["horizon_mean_mape"]
    frow["quarterly_bias_pct"] = paper_score["quarterly_bias_pct"]
    frow["quarterly_p90_ape"] = paper_score["quarterly_p90_ape"]
    frow["n_annual_pairs"] = paper_score["n_annual_pairs"]
    frow["annual_mape"] = paper_score["annual_mape"]
    frow["annual_bias_pct"] = paper_score["annual_bias_pct"]
    frow["annual_p90_ape"] = paper_score["annual_p90_ape"]
    frow["paper_horizon_mean_mape"] = paper_score["horizon_mean_mape"]
    frow["paper_pooled_mape"] = paper_score["quarterly_pooled_mape"]
    frow["paper_bias_pct"] = paper_score["quarterly_bias_pct"]
    frow["paper_annual_mape"] = paper_score["annual_mape"]
    frow["paper_annual_bias_pct"] = paper_score["annual_bias_pct"]
    frow["paper_h09_12_mape"] = paper_score["mape_h09_12"]
    frow["operational_pooled_mape"] = oper_score["quarterly_pooled_mape"]
    frow["operational_horizon_mean_mape"] = oper_score["horizon_mean_mape"]
    frow["operational_bias_pct"] = oper_score["quarterly_bias_pct"]
    frow["operational_annual_mape"] = oper_score["annual_mape"]
    frow["operational_annual_bias_pct"] = oper_score["annual_bias_pct"]
    frow["operational_h09_12_mape"] = oper_score["mape_h09_12"]
    frow["selection_note"] = (
        "AR(1) engine finalist: GLSAR AR(1)-error regression (Schiff-style levels + one lagged "
        "log target). Passes all six core diagnostics (Durbin-Watson, ADF, KPSS, Breusch-Pagan, "
        "White, cointegration); Jarque-Bera remains an advisory Watch. Selected from the "
        "Diagnostics Lab frontier at +0.09pp paper-grid MAPE vs the ML ensemble."
    )
    finalists = pd.concat([finalists[~fmask], frow.to_frame().T], ignore_index=True)
    _write("finalists", finalists)

    # ---- diagnostics battery ----------------------------------------------
    h1 = operational[operational["horizon"].eq(1)].sort_values("target_period")
    battery = run_battery(
        h1["actual"].to_numpy(float), h1["pred"].to_numpy(float), stream="PED"
    )
    s = battery.stats

    tests = _read("diagnostic_tests")
    tmask = tests["stream"].astype(str).eq("PED") & tests["role"].astype(str).str.contains("finalist", case=False)
    trow = tests[tmask].iloc[0].copy()
    a = pd.to_numeric(h1["actual"], errors="coerce").to_numpy(float)
    p = pd.to_numeric(h1["pred"], errors="coerce").to_numpy(float)
    trow.update(
        {
            "model": AR1_MODEL_NAME,
            "n_h1": battery.n,
            "mape_h1": vc.mape(a, p),
            "bias_h1_pct": vc.bias_pct(a, p),
            "p90_ape_h1": vc.p90_ape(a, p),
            "acf1_resid": float(pd.Series(a - p).autocorr(lag=1)),
            "durbin_watson": s["durbin_watson"],
            "ljungbox_p_lag4": s["ljungbox_p_lag4"],
            "ljungbox_p_lag8": s["ljungbox_p_lag8"],
            "ljungbox_p_lag12": s["ljungbox_p_lag12"],
            "adf_p_resid": s["adf_p_resid"],
            "kpss_p_resid": s["kpss_p_resid"],
            "jarque_bera_p": s["jarque_bera_p"],
            "skew_resid": s["skew_resid"],
            "kurtosis_resid": s["kurtosis_excess"],
            "shapiro_p": s["shapiro_p"],
            "breusch_pagan_p": s["breusch_pagan_p"],
            "white_p": s["white_p"],
            "arch_lm_p": s["arch_lm_p"],
            "coint_p_actual_pred": s["coint_p_actual_pred"],
            "mz_intercept": s["mz_intercept"],
            "mz_slope": s["mz_slope"],
            "mz_r2": s["mz_r2"],
            "mz_f_p": s["mz_f_p"],
            "calibration_r2": s["mz_r2"],
            "pass_no_autocorr_lb8": bool(s["ljungbox_p_lag8"] > 0.05),
            "pass_dw_range": battery.status["Durbin-Watson"] == "Pass",
            "pass_adf_stationary": battery.status["ADF"] == "Pass",
            "pass_kpss_stationary": battery.status["KPSS"] == "Pass",
            "pass_no_hetero_bp": battery.status["Breusch-Pagan"] == "Pass",
            "pass_no_arch": float(s["arch_lm_p"] > 0.05),
            "pass_coint": battery.status["Cointegration"] == "Pass",
            "pass_normal_jb": battery.status["Jarque-Bera"] == "Pass",
        }
    )
    tests = pd.concat([tests[~tmask], trow.to_frame().T], ignore_index=True)
    _write("diagnostic_tests", tests)

    stat_by_test = {
        "Calibration R2": (s["mz_r2"], s["mz_f_p"]),
        "Durbin-Watson": (s["durbin_watson"], s["ljungbox_p_lag8"]),
        "ADF": (s["adf_stat"], s["adf_p_resid"]),
        "KPSS": (s["kpss_stat"], s["kpss_p_resid"]),
        "Breusch-Pagan": (s["breusch_pagan_stat"], s["breusch_pagan_p"]),
        "White": (s["white_stat"], s["white_p"]),
        "Jarque-Bera": (s["jarque_bera_stat"], s["jarque_bera_p"]),
        "Cointegration": (s["coint_stat"], s["coint_p_actual_pred"]),
        "Overall": (float("nan"), float("nan")),
    }
    extra_by_test = {
        "Calibration R2": {"mz_intercept": s["mz_intercept"], "mz_slope": s["mz_slope"]},
        "Durbin-Watson": {"ideal": 2.0, "pass_band": [1.5, 2.5]},
        "ADF": {"lags_used": int(s["adf_lags"])},
        "KPSS": {"lags_used": int(s["kpss_lags"])},
        "Breusch-Pagan": {"regressors": "fitted value + time index"},
        "White": {"regressors": "fitted value + time index, squares and cross-terms"},
        "Jarque-Bera": {"skew": s["skew_resid"], "kurtosis_excess": s["kurtosis_excess"]},
        "Cointegration": {"critical_value_5pct": s["coint_crit_5pct"]},
        "Overall": {
            "core_tests": ["Durbin-Watson", "ADF", "KPSS", "Breusch-Pagan", "White", "Cointegration"],
            "advisory_tests": ["Jarque-Bera"],
            "arch_lm_p_companion": s["arch_lm_p"],
        },
    }
    detail = _read("diagnostic_test_detail")
    dmask = detail["stream"].astype(str).eq("PED")
    drows = []
    for _, row in detail[dmask].iterrows():
        test = str(row["diagnostic_test"])
        new = row.copy()
        new["model"] = AR1_MODEL_NAME
        stat, pval = stat_by_test[test]
        new["statistic"] = stat
        new["p_value"] = pval
        new["pass_status"] = battery.status.get(test, battery.overall if test == "Overall" else "Unavailable")
        if test == "Overall":
            new["pass_status"] = battery.overall
        new["n_rows"] = battery.n
        new["source_dataset"] = "scorecard_predictions.parquet (AR(1) finalist, operational grid, h=1)"
        new["extra_json"] = json.dumps(extra_by_test[test])
        drows.append(new)
    detail = pd.concat([detail[~dmask], pd.DataFrame(drows)], ignore_index=True)
    _write("diagnostic_test_detail", detail)

    matrix = _read("diagnostic_pass_matrix")
    mmask = matrix["stream"].astype(str).eq("PED")
    mrows = []
    for _, row in matrix[mmask].iterrows():
        test = str(row["diagnostic_test"])
        new = row.copy()
        new["model"] = AR1_MODEL_NAME
        new["pass_status"] = battery.overall if test == "Overall" else battery.status.get(test, "Unavailable")
        new["source_dataset"] = "scorecard_predictions.parquet (AR(1) finalist, operational grid, h=1)"
        mrows.append(new)
    matrix = pd.concat([matrix[~mmask], pd.DataFrame(mrows)], ignore_index=True)
    _write("diagnostic_pass_matrix", matrix)

    acf_frame = _read("diagnostic_acf")
    amask = acf_frame["stream"].astype(str).eq("PED")
    from statsmodels.tsa.stattools import acf as sm_acf

    resid = a - p
    acf_vals = sm_acf(resid, nlags=int(pd.to_numeric(acf_frame[amask]["lag"], errors="coerce").max()), fft=False)
    arows = []
    for _, row in acf_frame[amask].iterrows():
        new = row.copy()
        new["model"] = AR1_MODEL_NAME
        lag = int(row["lag"])
        new["acf_value"] = float(acf_vals[lag]) if lag < len(acf_vals) else float("nan")
        arows.append(new)
    acf_frame = pd.concat([acf_frame[~amask], pd.DataFrame(arows)], ignore_index=True)
    _write("diagnostic_acf", acf_frame)

    # ---- registry / components / coefficients ------------------------------
    registry = _read("model_registry")
    rmask = registry["stream"].astype(str).eq("PED")
    rtmpl = registry[rmask].iloc[0].copy()
    reg_rows = []
    for role, component in (("finalist", AR1_MODEL_NAME), ("component", AR1_MODEL_NAME)):
        new = rtmpl.copy()
        new["model"] = AR1_MODEL_NAME
        new["component_model"] = component
        new["model_role"] = role
        new["algorithm"] = "glsar_ar1"
        new["feature_set"] = "schiff_levels_trend_seasonal"
        new["feature_columns"] = json.dumps(list(state["features"]) + [f"target__ylag{l}" for l in state["ylags"]])
        new["window_type"] = "expanding"
        new["window_length"] = None
        new["hyperparameters_json"] = json.dumps({"ar": state["ar_order"], "glsar_max_iter": state["glsar_max_iter"], "ylags": state["ylags"]})
        new["random_state"] = None
        new["source_script"] = "pipeline/ar1_engine.py"
        new["component_weight"] = 1.0
        new["reproducibility_status"] = "production_forward_scoreable"
        new["reproducibility_note"] = "Deterministic linear refit gate; state in dashboard_evidence_pack_reproducibility/ped_ar1."
        reg_rows.append(new)
    registry = pd.concat([registry[~rmask], pd.DataFrame(reg_rows)], ignore_index=True)
    _write("model_registry", registry)

    components = _read("ensemble_components")
    cmask = components["stream"].astype(str).eq("PED")
    crow = components[cmask].iloc[0].copy()
    crow["finalist_model"] = AR1_MODEL_NAME
    crow["finalist_model_short"] = MODEL_SHORT
    crow["component_rank"] = 1
    crow["component_model"] = AR1_MODEL_NAME
    crow["component_short"] = MODEL_SHORT
    crow["weight"] = 1.0
    crow["weight_pct"] = 100.0
    components = pd.concat([components[~cmask], crow.to_frame().T], ignore_index=True)
    _write("ensemble_components", components)

    coefficients = _read("model_coefficients")
    comask = coefficients["stream"].astype(str).eq("PED")
    cotmpl = coefficients[comask].iloc[0].copy()
    names = ["const"] + list(state["features"]) + [f"target__ylag{l}" for l in state["ylags"]]
    corows = []
    for name, beta in zip(names, state["beta"]):
        new = cotmpl.copy()
        new["model"] = AR1_MODEL_NAME
        new["component_model"] = AR1_MODEL_NAME
        new["feature"] = name
        new["coefficient"] = float(beta)
        new["intercept"] = float(state["beta"][0])
        new["standardised_coefficient"] = np.nan
        new["origin"] = "production"
        new["window_start"] = state["train_window_start"]
        new["window_end"] = state["train_window_end"]
        new["reproducibility_status"] = "production_forward_scoreable"
        new["notes"] = "GLSAR AR(1) coefficient (log-target space)."
        new["artifact_search_status"] = "found"
        corows.append(new)
    for i, rho in enumerate(state["rho"], start=1):
        new = cotmpl.copy()
        new["model"] = AR1_MODEL_NAME
        new["component_model"] = AR1_MODEL_NAME
        new["feature"] = f"rho_{i}"
        new["coefficient"] = float(rho)
        new["intercept"] = float(state["beta"][0])
        new["standardised_coefficient"] = np.nan
        new["origin"] = "production"
        new["window_start"] = state["train_window_start"]
        new["window_end"] = state["train_window_end"]
        new["reproducibility_status"] = "production_forward_scoreable"
        new["notes"] = "AR(1) error autocorrelation coefficient."
        new["artifact_search_status"] = "found"
        corows.append(new)
    coefficients = pd.concat([coefficients[~comask], pd.DataFrame(corows)], ignore_index=True)
    _write("model_coefficients", coefficients)

    # ---- component predictions (single component == final) ----------------
    comp = _read("component_predictions")
    cpmask = comp["stream"].astype(str).eq("PED")
    cp_tmpl_cols = comp.columns
    cp_rows = ar1_rows.copy()
    cp = pd.DataFrame(
        {
            "stream": "PED",
            "stream_label": cp_rows["stream_label"],
            "finalist_model": AR1_MODEL_NAME,
            "component_model": AR1_MODEL_NAME,
            "score_basis": cp_rows["score_basis"],
            "origin": cp_rows["origin"],
            "target_period": cp_rows["target_period"],
            "horizon": cp_rows["horizon"],
            "actual": cp_rows["actual"],
            "component_pred": cp_rows["pred"],
            "component_error_pct": cp_rows["error_pct"],
            "component_abs_error_pct": cp_rows["abs_error_pct"],
            "component_weight": 1.0,
            "weighted_component_pred": cp_rows["pred"],
            "final_pred": cp_rows["pred"],
            "component_traceability_status": "production_forward_scoreable",
            "source": SOURCE_DATASET,
            "source_basis": "single_linear_component",
        }
    ).reindex(columns=cp_tmpl_cols)
    comp = pd.concat([comp[~cpmask], cp], ignore_index=True)
    _write("component_predictions", comp)

    # ---- importance-style tables -------------------------------------------
    importance = _read("feature_importance")
    imask = importance["stream"].astype(str).eq("PED")
    itmpl = importance[imask].iloc[0].copy()
    betas = list(zip(names[1:], state["beta"][1:]))
    order = sorted(betas, key=lambda kv: abs(kv[1]), reverse=True)
    irows = []
    for rank, (name, beta) in enumerate(order, start=1):
        new = itmpl.copy()
        new["model"] = AR1_MODEL_NAME
        new["origin_or_global"] = "global"
        new["feature"] = name
        new["importance_type"] = "abs_coefficient"
        new["importance_value"] = abs(float(beta))
        new["rank"] = rank
        new["reproducibility_status"] = "production_forward_scoreable"
        new["notes"] = "Absolute GLSAR coefficient magnitude (log-target space)."
        new["artifact_search_status"] = "found"
        irows.append(new)
    importance = pd.concat([importance[~imask], pd.DataFrame(irows)], ignore_index=True)
    _write("feature_importance", importance)

    for name in ("shap_summary", "scenario_sensitivities"):
        frame = _read(name)
        frame = frame[~frame["stream"].astype(str).eq("PED")].reset_index(drop=True)
        _write(name, frame)

    # ---- paired vs schiff + scenario_comparison ----------------------------
    schiff = vc.load_schiff_predictions(REPO_ROOT, "PED")
    win_rate = vc.paired_win_rate(paper, schiff, vc.PAPER_SCORE_BASIS)
    for name, win_col, pairs_col in (
        ("paired_vs_schiff", "challenger_win_rate", "n_common_pairs"),
        ("scenario_comparison", "paired_win_rate_pct", "paired_common_pairs"),
    ):
        frame = _read(name)
        pmask = frame["stream"].astype(str).eq("PED")
        prow = frame[pmask].iloc[0].copy()
        schiff_qtr = float(prow["schiff_quarterly_mape"])
        schiff_ann = float(prow["schiff_annual_mape"])
        prow["finalist_quarterly_mape"] = paper_score["horizon_mean_mape"]
        prow["finalist_annual_mape"] = paper_score["annual_mape"]
        prow["full_sample_qtr_gain_pp"] = schiff_qtr - paper_score["horizon_mean_mape"]
        prow["full_sample_annual_gain_pp"] = schiff_ann - paper_score["annual_mape"]
        prow[win_col] = win_rate
        if "challenger_mape" in prow.index:
            prow["challenger_mape"] = paper_score["horizon_mean_mape"]
        if "paired_finalist_mape" in prow.index:
            prow["paired_finalist_mape"] = paper_score["horizon_mean_mape"]
        prow["operational_finalist_mape"] = oper_score["quarterly_pooled_mape"]
        prow["operational_gain_pp"] = float(prow["operational_schiff_mape"]) - oper_score["quarterly_pooled_mape"]
        if "challenger" in prow.index:
            prow["challenger"] = "Current finalist"
        frame = pd.concat([frame[~pmask], prow.to_frame().T], ignore_index=True)
        _write(name, frame)

    # ---- candidate cone -----------------------------------------------------
    cone = _read("candidate_cone")
    rec_mask = cone["stream"].astype(str).eq("PED") & cone["is_current_recommended"].astype(bool)
    new_row = cone[rec_mask].iloc[0].copy()
    cone.loc[rec_mask, "is_current_recommended"] = False
    cone.loc[rec_mask, "candidate_role"] = "previous_recommended"
    new_row["candidate_uid"] = AR1_CANDIDATE_UID
    new_row["model"] = AR1_MODEL_NAME
    new_row["model_short"] = MODEL_SHORT
    new_row["run_source"] = "diagnostics_lab"
    new_row["source_file"] = "artifacts/diagnostics_lab/ped/winners"
    new_row["source_family"] = "ar1_engine"
    new_row["model_kind"] = "glsar_ar1"
    new_row["feature_set"] = "schiff_levels_trend_seasonal"
    for key, value in (
        ("n_quarterly_pairs", paper_score["n_quarterly_pairs"]),
        ("n_origins", paper_score["n_origins"]),
        ("quarterly_mape", paper_score["horizon_mean_mape"]),
        ("annual_mape", paper_score["annual_mape"]),
        ("quarterly_bias_pct", paper_score["quarterly_bias_pct"]),
        ("annual_bias_pct", paper_score["annual_bias_pct"]),
        ("quarterly_p90_ape", paper_score["quarterly_p90_ape"]),
        ("annual_p90_ape", paper_score["annual_p90_ape"]),
        ("mape_h01_04", paper_score["mape_h01_04"]),
        ("mape_h05_08", paper_score["mape_h05_08"]),
        ("mape_h09_12", paper_score["mape_h09_12"]),
        ("paper_horizon_mean_mape", paper_score["horizon_mean_mape"]),
        ("paper_pooled_mape", paper_score["quarterly_pooled_mape"]),
        ("paper_bias_pct", paper_score["quarterly_bias_pct"]),
        ("paper_annual_mape", paper_score["annual_mape"]),
        ("paper_h09_12_mape", paper_score["mape_h09_12"]),
        ("operational_pooled_mape", oper_score["quarterly_pooled_mape"]),
        ("operational_horizon_mean_mape", oper_score["horizon_mean_mape"]),
        ("operational_bias_pct", oper_score["quarterly_bias_pct"]),
        ("operational_annual_mape", oper_score["annual_mape"]),
        ("is_current_recommended", True),
        ("candidate_role", "current_recommended"),
        ("include_reason", "AR(1) engine finalist (Diagnostics Lab all-core-pass winner)"),
        ("is_curated_cone_sample", False),
    ):
        if key in new_row.index:
            new_row[key] = value
    cone = pd.concat([cone, new_row.to_frame().T], ignore_index=True)
    _write("candidate_cone", cone)

    # ---- manifest -----------------------------------------------------------
    manifest_path = DST / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["engine"] = "ar1"
    manifest["engine_note"] = (
        "AR(1) alternate engine pack: the PED finalist is the GLSAR AR(1) regression "
        "from the Diagnostics Lab; Light RUC and Heavy RUC are identical to the incumbent pack."
    )
    manifest["created_at"] = datetime.now(timezone.utc).isoformat()
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"AR1 evidence pack written: {DST}")
    print(f"PED finalist paper MAPE {paper_score['horizon_mean_mape']:.4f} / annual {paper_score['annual_mape']:.4f}")
    print(f"battery: core {battery.core_passes}/6, overall {battery.overall}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

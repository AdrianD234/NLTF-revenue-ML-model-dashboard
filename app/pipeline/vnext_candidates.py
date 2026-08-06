"""Governed vNext candidate grids.

Two layers per stream:
1. Locked-spec refits — the exact component families/hyperparameters/windows of
   the archived finalists, refit on the canonical repo input history.
2. Challenger grid — disciplined variations within the allowed families
   (ElasticNet, Ridge, OLS, GBM, OLS-base + GBM-residual; ylag/no-ylag;
   rolling windows). No broad search, no leads.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .vnext_core import RANDOM_STATE, CandidateSpec, make_spec

GBR_FIXED = {"loss": "squared_error", "subsample": 0.85, "random_state": RANDOM_STATE}
EN_FIXED = {"max_iter": 50000, "random_state": RANDOM_STATE}


# ---------------------------------------------------------------------------
# Locked-spec refit components (archived finalist lineage)
# ---------------------------------------------------------------------------

def heavy_locked_refit_components() -> List[CandidateSpec]:
    """Refit analogues of the archived HEAVY_RUC__RECON_STATIC_REBUILT C1-C4."""
    return [
        make_spec("HEAVY_RUC", "elastic_net", {"alpha": 0.005, "l1_ratio": 0.2, **EN_FIXED},
                  64, "dynamic_no_leads", True, "locked_refit_C1"),
        make_spec("HEAVY_RUC", "gbr", {"learning_rate": 0.06, "max_depth": 1, "n_estimators": 650, **GBR_FIXED},
                  64, "schiff", False, "locked_refit_C2"),
        make_spec("HEAVY_RUC", "gbr", {"learning_rate": 0.08, "max_depth": 1, "n_estimators": 400, **GBR_FIXED},
                  52, "dynamic_no_leads", True, "locked_refit_C3"),
        make_spec("HEAVY_RUC", "gbr", {"learning_rate": 0.08, "max_depth": 1, "n_estimators": 150, **GBR_FIXED},
                  40, "dynamic_no_leads", True, "locked_refit_C4"),
    ]


HEAVY_LOCKED_WEIGHTS = [0.469332, 0.281844, 0.144373, 0.104451]


def ped_locked_refit_components() -> List[CandidateSpec]:
    """Refit analogues of the PED inner static-solver members.

    The archived inner chain was static_convex_top18 + preq_convex_top18 +
    diff GBR (lr 0.05, depth 1, n 650, ylag, w40). The convex-top18 members
    were never retained, so the refit layer uses the governed family
    analogues: static OLS/EN/Ridge and the diff GBR member.
    """
    return [
        make_spec("PED", "ols", {}, None, "static", False, "locked_refit_static"),
        make_spec("PED", "elastic_net", {"alpha": 0.005, "l1_ratio": 0.2, **EN_FIXED},
                  None, "static", False, "locked_refit_static_en"),
        make_spec("PED", "gbr", {"learning_rate": 0.05, "max_depth": 1, "n_estimators": 650, **GBR_FIXED},
                  40, "diff", True, "locked_refit_diff_gbr"),
    ]


# ---------------------------------------------------------------------------
# Challenger grids
# ---------------------------------------------------------------------------

def heavy_challengers() -> List[CandidateSpec]:
    out: List[CandidateSpec] = []
    # ElasticNet family
    for alpha in (0.003, 0.005, 0.01):
        for l1 in (0.2, 0.5):
            for w in (52, 64):
                out.append(make_spec("HEAVY_RUC", "elastic_net",
                                     {"alpha": alpha, "l1_ratio": l1, **EN_FIXED},
                                     w, "dynamic_no_leads", True, "challenger_en"))
    # Ridge
    for alpha in (1.0, 10.0):
        for w in (52, 64):
            out.append(make_spec("HEAVY_RUC", "ridge", {"alpha": alpha, "random_state": RANDOM_STATE},
                                 w, "dynamic_no_leads", True, "challenger_ridge"))
    # OLS on schiff spec (paper baseline family)
    for w in (None, 64):
        out.append(make_spec("HEAVY_RUC", "ols", {}, w, "schiff", False, "challenger_ols_schiff"))
    # GBR family (ylag and noylag, several windows)
    for lr in (0.05, 0.06, 0.08):
        for n in (150, 400, 650):
            for w in (40, 52, 64):
                for ylag, fs in ((True, "dynamic_no_leads"), (False, "schiff"), (False, "dynamic_no_leads")):
                    out.append(make_spec("HEAVY_RUC", "gbr",
                                         {"learning_rate": lr, "max_depth": 1, "n_estimators": n, **GBR_FIXED},
                                         w, fs, ylag, "challenger_gbr"))
    # Light-RUC-style two-stage: OLS schiff base + GBM residual on dynamic features
    for n in (150, 400):
        for lr in (0.05, 0.08):
            for w in (40, 52, 64):
                out.append(make_spec("HEAVY_RUC", "resid_gbr",
                                     {"learning_rate": lr, "max_depth": 1, "n_estimators": n, **GBR_FIXED},
                                     w, "dynamic_no_leads", False, "challenger_resid_gbr",
                                     base_feature_set="schiff"))
    return out


def ped_challengers() -> List[CandidateSpec]:
    out: List[CandidateSpec] = []
    for alpha in (0.001, 0.005, 0.01):
        for l1 in (0.2, 0.5):
            for w in (None, 48, 64):
                out.append(make_spec("PED", "elastic_net",
                                     {"alpha": alpha, "l1_ratio": l1, **EN_FIXED},
                                     w, "static", False, "challenger_en_static"))
    for alpha in (1.0, 10.0):
        for w in (None, 64):
            out.append(make_spec("PED", "ridge", {"alpha": alpha, "random_state": RANDOM_STATE},
                                 w, "static", False, "challenger_ridge_static"))
    for w in (None, 48, 64):
        out.append(make_spec("PED", "ols", {}, w, "schiff", False, "challenger_ols_schiff"))
        out.append(make_spec("PED", "ols", {}, w, "static", False, "challenger_ols_static"))
    for lr in (0.05, 0.08):
        for n in (150, 400, 650):
            for w in (40, 56, None):
                for ylag, fs in ((True, "diff"), (True, "dynamic_no_leads"), (False, "dynamic_no_leads")):
                    out.append(make_spec("PED", "gbr",
                                         {"learning_rate": lr, "max_depth": 1, "n_estimators": n, **GBR_FIXED},
                                         w, fs, ylag, "challenger_gbr"))
    for n in (150, 400):
        for lr in (0.05, 0.08):
            for w in (None, 48, 64):
                out.append(make_spec("PED", "resid_gbr",
                                     {"learning_rate": lr, "max_depth": 1, "n_estimators": n, **GBR_FIXED},
                                     w, "dynamic_no_leads", False, "challenger_resid_gbr",
                                     base_feature_set="schiff"))
    return out


def candidate_grid(stream: str) -> List[CandidateSpec]:
    if stream == "HEAVY_RUC":
        return heavy_locked_refit_components() + heavy_challengers()
    if stream == "PED":
        return ped_locked_refit_components() + ped_challengers()
    raise ValueError(f"No vNext grid for stream {stream}")

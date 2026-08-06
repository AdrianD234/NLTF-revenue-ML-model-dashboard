"""Diagnostics Lab orchestrator: adaptive, self-correcting search over remedy arms.

Successive-halving flavour: every arm gets a small seed grid in round 1;
later rounds allocate budget toward promising arms (lexicographic promise =
core passes, then paper-grid MAPE), retire stalled arms, and - the
self-correcting part - inspect WHICH core tests an arm's best candidate
still fails and compose the matching remedy layer (WLS for White/BP, pulse
dummies for Jarque-Bera, deeper AR structure for Durbin-Watson) instead of
digging further in the same grid.

Rounds are run one CLI invocation at a time; each round writes
``artifacts/diagnostics_lab/<stream>/round_N/{candidates.parquet, report.md}``
plus a cumulative ``state.json`` so a human (or Claude) can judge results
and steer before the next round.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from pipeline import vnext_core as vc
from pipeline.diaglab_arms import (
    FINALIST_MODELS,
    DiagData,
    DiagSpec,
    compose_pulses,
    compose_weight,
    evaluate_spec,
    feature_bundle,
    load_diag_data,
)
from pipeline.diaglab_battery import CORE_TESTS

LAB_DIR = Path("artifacts") / "diagnostics_lab"
RETIRE_AFTER_STALL_ROUNDS = 2
CORE_PASS_RETIREMENT_GAP = 3


# ---------------------------------------------------------------------------
# Seed grids (round 1)
# ---------------------------------------------------------------------------
def seed_grid(stream: str) -> List[DiagSpec]:
    specs: List[DiagSpec] = []
    if stream == "PED":
        core = feature_bundle(stream, ["levels", "trend", "seasonal"])
        rich = feature_bundle(stream, ["levels", "trend", "seasonal", "policy"])
        for features, tag in ((core, "core"), (rich, "rich")):
            for ylags in ((1,), (1, 4)):
                for window in (None, 56):
                    specs.append(DiagSpec(stream, "A", "arx", features, window, ylags=ylags, label=tag))
        for features, tag in ((core, "core"), (rich, "rich")):
            for ar in (1, 2):
                specs.append(DiagSpec(stream, "B", "glsar", features, None, params_json=json.dumps({"ar": ar}), label=tag))
        sarimax_exog = feature_bundle(stream, ["levels", "trend"])
        for order, seasonal in (
            ((1, 0, 0), (0, 0, 0, 0)),
            ((2, 0, 0), (0, 0, 0, 0)),
            ((1, 0, 1), (0, 0, 0, 0)),
            ((1, 0, 0), (1, 0, 0, 4)),
            ((1, 0, 1), (1, 0, 0, 4)),
        ):
            specs.append(
                DiagSpec(stream, "C", "sarimax", sarimax_exog, None,
                         params_json=json.dumps({"order": list(order), "seasonal": list(seasonal)}))
            )
        for window in (None, 56):
            specs.append(DiagSpec(stream, "D", "ecm", feature_bundle(stream, ["levels"]), window))
    elif stream == "LIGHT_RUC":
        # Arm R: the production recipe itself (OLS base + GBM residual
        # correction, w36) with JB remedies composed onto the OLS base -
        # the finalist's only blemish is a Jarque-Bera Watch, so the first
        # question is whether the incumbent architecture can shed it.
        recipe = DiagSpec(stream, "R", "light_recipe", tuple(), 36)
        specs.append(recipe)
        specs.append(compose_pulses(recipe))
        specs.append(compose_weight(recipe, "covid_down"))
        specs.append(compose_weight(recipe, "regime_var"))
        specs.append(compose_pulses(compose_weight(recipe, "covid_down")))
        specs.append(DiagSpec(stream, "R", "light_recipe", tuple(), 44))
        specs.append(compose_pulses(DiagSpec(stream, "R", "light_recipe", tuple(), 44)))
        base = feature_bundle(stream, ["levels", "trend", "seasonal"])
        for ylags in ((), (1,)):
            for window in (36, None):
                specs.append(DiagSpec(stream, "A", "arx", base, window, ylags=ylags, label="base"))
        for ar in (1,):
            specs.append(DiagSpec(stream, "B", "glsar", base, 36, params_json=json.dumps({"ar": ar}), label="base"))
            specs.append(DiagSpec(stream, "B", "glsar", base, None, params_json=json.dumps({"ar": ar}), label="base"))
        specs.extend(compose_pulses(s) for s in list(specs) if s.kind in {"arx", "glsar"} and s.window == 36 and not s.pulses)
    else:  # HEAVY_RUC sanity check
        core = feature_bundle(stream, ["levels", "trend", "seasonal"])
        specs.append(DiagSpec(stream, "A", "arx", core, None, ylags=(1,)))
        specs.append(DiagSpec(stream, "B", "glsar", core, None, params_json=json.dumps({"ar": 1})))
    return specs


# ---------------------------------------------------------------------------
# Composition-driven follow-ups (rounds >= 2)
# ---------------------------------------------------------------------------
def followups_for(spec_row: Dict[str, Any], spec: DiagSpec) -> List[DiagSpec]:
    """Remedy-layer compositions based on the candidate's remaining failures."""
    fails = {t for t in CORE_TESTS if spec_row.get(f"status__{t.replace(' ', '_')}") == "Fail"}
    jb_watch = spec_row.get("status__Jarque-Bera") == "Watch"
    out: List[DiagSpec] = []
    if {"White", "Breusch-Pagan"} & fails:
        if spec.weight_mode is None:
            out.append(compose_weight(spec, "covid_down"))
            out.append(compose_weight(spec, "regime_var"))
    if jb_watch and not spec.pulses and spec.kind in {"arx", "glsar"}:
        out.append(compose_pulses(spec))
    if "Durbin-Watson" in fails:
        if spec.kind == "arx":
            lags = tuple(sorted(set(spec.ylags) | {1, 4}))
            if lags != spec.ylags:
                out.append(replace(spec, ylags=lags))
        elif spec.kind == "glsar":
            ar = int(spec.params.get("ar", 1))
            if ar < 4:
                out.append(replace(spec, params_json=json.dumps({"ar": ar + 1})))
            # Dynamic mean term: the AR error alone may under-absorb the
            # persistence the h1 backtest residuals inherit from the mean.
            if not spec.ylags:
                out.append(replace(spec, ylags=(1,)))
                out.append(replace(spec, ylags=(1, 4)))
        elif spec.kind == "sarimax":
            p_ = spec.params
            order = list(p_.get("order", [1, 0, 0]))
            order[0] = min(order[0] + 1, 4)
            out.append(replace(spec, params_json=json.dumps({"order": order, "seasonal": p_.get("seasonal", [0, 0, 0, 0])})))
        elif spec.kind == "ecm" and int(spec.params.get("dylag", 0)) == 0:
            out.append(replace(spec, params_json=json.dumps({**spec.params, "dylag": 1})))
    return out


def neighbourhood(spec: DiagSpec) -> List[DiagSpec]:
    """Small deterministic neighbourhood around a promising spec."""
    out: List[DiagSpec] = []
    if spec.window is None:
        out.append(replace(spec, window=56 if spec.stream == "PED" else 44))
    else:
        out.append(replace(spec, window=None))
    if spec.kind == "arx" and spec.ylags == (1,):
        out.append(replace(spec, ylags=(1, 2)))
    if spec.kind == "sarimax":
        p_ = spec.params
        seasonal = list(p_.get("seasonal", [0, 0, 0, 0]))
        if seasonal[0] == 0:
            out.append(replace(spec, params_json=json.dumps({"order": p_.get("order", [1, 0, 0]), "seasonal": [1, 0, 0, 4]})))
    return out


# ---------------------------------------------------------------------------
# State + scoring
# ---------------------------------------------------------------------------
def candidate_sort_key(row: Dict[str, Any]) -> tuple:
    mape = row.get("paper_horizon_mean_mape")
    mape = float(mape) if mape is not None and np.isfinite(mape) else float("inf")
    return (
        -int(row.get("core_passes", 0)),
        0 if row.get("status__Jarque-Bera") == "Pass" else 1,
        mape,
    )


def load_state(stream_dir: Path) -> Dict[str, Any]:
    path = stream_dir / "state.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"round": 0, "arms": {}, "tried": []}


def save_state(stream_dir: Path, state: Dict[str, Any]) -> None:
    (stream_dir / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")


def _spec_from_row(row: Dict[str, Any]) -> DiagSpec:
    window = row.get("window")
    window_val = None if window in (None, "expanding") else int(window)
    ylags = tuple(int(x) for x in str(row.get("ylags", "")).split(",") if str(x).strip())
    return DiagSpec(
        stream=str(row["stream"]),
        arm=str(row["arm"]),
        kind=str(row["kind"]),
        features=tuple(json.loads(row["features_json"])),
        window=window_val,
        ylags=ylags,
        params_json=str(row.get("params_json", "{}")),
        weight_mode=(str(row["weight_mode"]) or None) if row.get("weight_mode") else None,
        pulses=bool(row.get("pulses", False)),
    )


def finalist_reference(repo_root: Path, stream: str) -> Dict[str, Any]:
    fin = pd.read_parquet(repo_root / "data/dashboard_evidence_pack/data/finalists.parquet")
    row = fin[fin["stream"].astype(str).eq(stream)].iloc[0]
    matrix = pd.read_parquet(repo_root / "data/dashboard_evidence_pack/data/diagnostic_pass_matrix.parquet")
    governed = matrix[matrix["stream"].astype(str).eq(stream)].set_index("diagnostic_test")["pass_status"]
    return {
        "model": str(row["model"]),
        "paper_horizon_mean_mape": float(row["paper_horizon_mean_mape"]),
        "paper_annual_mape": float(row["paper_annual_mape"]),
        "core_passes": int(sum(1 for t in CORE_TESTS if str(governed.get(t)) == "Pass")),
        "overall": str(governed.get("Overall")),
    }


# ---------------------------------------------------------------------------
# Round runner
# ---------------------------------------------------------------------------
def run_round(
    repo_root: Path,
    stream: str,
    *,
    budget: int = 40,
    steer: Optional[Dict[str, Any]] = None,
) -> Path:
    steer = steer or {}
    stream_dir = Path(repo_root) / LAB_DIR / stream.lower()
    stream_dir.mkdir(parents=True, exist_ok=True)
    state = load_state(stream_dir)
    round_n = int(state["round"]) + 1
    round_dir = stream_dir / f"round_{round_n}"
    round_dir.mkdir(parents=True, exist_ok=True)

    dd = load_diag_data(Path(repo_root), stream)
    keysets = vc.load_eval_keysets(Path(repo_root), stream, FINALIST_MODELS[stream])
    origin_labels = sorted(
        set().union(*(set(k["origin"].astype(str)) for k in keysets.values() if not k.empty))
    )
    origins = [vc.parse_period(o) for o in origin_labels]

    prev_rows: List[Dict[str, Any]] = state.get("all_rows", [])
    tried = set(state.get("tried", []))

    if round_n == 1:
        specs = seed_grid(stream)
    else:
        specs = []
        arm_best: Dict[str, Dict[str, Any]] = {}
        for row in prev_rows:
            arm = str(row["arm"])
            if arm not in arm_best or candidate_sort_key(row) < candidate_sort_key(arm_best[arm]):
                arm_best[arm] = row
        ranked_arms = sorted(arm_best, key=lambda a: candidate_sort_key(arm_best[a]))
        best_core = max((int(r.get("core_passes", 0)) for r in arm_best.values()), default=0)
        retired = set(state.get("retired_arms", [])) | set(steer.get("retire_arms", []))
        quotas = steer.get("arm_quotas") or {}
        for rank, arm in enumerate(ranked_arms):
            if arm in retired:
                continue
            row = arm_best[arm]
            if int(row.get("core_passes", 0)) <= best_core - CORE_PASS_RETIREMENT_GAP:
                retired.add(arm)
                continue
            spec = _spec_from_row(row)
            quota = int(quotas.get(arm, max(2, budget // (2 ** (rank + 1)))))
            follow = followups_for(row, spec) + neighbourhood(spec)
            specs.extend(follow[:quota])
        state["retired_arms"] = sorted(retired)
        for extra in steer.get("extra_specs", []):
            specs.append(_spec_from_row(extra))

    specs = [s for s in specs if s.name not in tried][: int(steer.get("max_configs", budget))]

    rows: List[Dict[str, Any]] = []
    for spec in specs:
        if spec.kind == "vnext":
            params = json.loads(spec.params_json)
            params["repo_root"] = str(repo_root)
            spec = replace(spec, params_json=json.dumps(params))
        result = evaluate_spec(dd, spec, keysets, origins)
        tried.add(spec.name)
        if result is not None:
            rows.append(result)

    all_rows = prev_rows + rows
    state.update({"round": round_n, "tried": sorted(tried), "all_rows": all_rows})
    save_state(stream_dir, state)

    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame = frame.iloc[sorted(range(len(frame)), key=lambda i: candidate_sort_key(frame.iloc[i].to_dict()))]
    frame.to_parquet(round_dir / "candidates.parquet", index=False)
    _write_report(Path(repo_root), stream, round_n, round_dir, rows, all_rows)
    return round_dir


def export_winners(repo_root: Path, stream: str, top_n: int = 2) -> Path:
    """Re-backtest the leading candidates and write promotion-ready artifacts.

    Emits, per winner, the full rolling-origin prediction rows (vNext
    ``scorecard_predictions`` schema subset) plus a registry-style summary
    JSON, so a future alternate-engine promotion needs no re-estimation.
    """
    from pipeline.diaglab_arms import backtest_spec

    stream_dir = Path(repo_root) / LAB_DIR / stream.lower()
    state = load_state(stream_dir)
    rows = state.get("all_rows", [])
    if not rows:
        raise SystemExit(f"no candidates for {stream}; run rounds first")
    ranked = sorted(rows, key=candidate_sort_key)
    winners: List[Dict[str, Any]] = []
    all_pass = [r for r in ranked if int(r.get("core_passes", 0)) == 6]
    if all_pass:
        winners.append(all_pass[0])
    by_mape = sorted(
        (r for r in rows if r.get("paper_horizon_mean_mape") is not None and np.isfinite(float(r["paper_horizon_mean_mape"]))),
        key=lambda r: float(r["paper_horizon_mean_mape"]),
    )
    for row in by_mape:
        if len(winners) >= top_n:
            break
        if row["model"] not in {w["model"] for w in winners}:
            winners.append(row)

    out_dir = stream_dir / "winners"
    out_dir.mkdir(parents=True, exist_ok=True)
    dd = load_diag_data(Path(repo_root), stream)
    keysets = vc.load_eval_keysets(Path(repo_root), stream, FINALIST_MODELS[stream])
    origins = sorted({vc.parse_period(o) for k in keysets.values() for o in k["origin"].astype(str)})
    for row in winners:
        spec = _spec_from_row(row)
        preds = backtest_spec(dd, spec, origins)
        safe = str(row["model"]).replace("/", "_")[:120]
        preds.to_parquet(out_dir / f"{safe}.predictions.parquet", index=False)
        summary = {
            "model": row["model"],
            "stream": stream,
            "arm": row["arm"],
            "kind": row["kind"],
            "algorithm": row["kind"],
            "feature_set": json.loads(row["features_json"]),
            "window_type": "rolling" if row.get("window") not in (None, "expanding") else "expanding",
            "window_length": None if row.get("window") in (None, "expanding") else int(row["window"]),
            "hyperparameters_json": row.get("params_json", "{}"),
            "ylags": row.get("ylags", ""),
            "weight_mode": row.get("weight_mode", ""),
            "pulses": bool(row.get("pulses", False)),
            "source_script": "pipeline/diaglab_orchestrator.py",
            "battery": {k: v for k, v in row.items() if k.startswith(("stat__", "status__"))},
            "scores": {
                k: row.get(k)
                for k in (
                    "paper_horizon_mean_mape", "paper_pooled_mape", "paper_annual_mape",
                    "paper_n_pairs", "mape_h01_04", "mape_h05_08", "mape_h09_12",
                )
            },
        }
        (out_dir / f"{safe}.summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return out_dir


def _fmt_mape(value: Any) -> str:
    try:
        v = float(value)
        return f"{v:.2f}%" if np.isfinite(v) else "-"
    except (TypeError, ValueError):
        return "-"


def _status_compact(row: Dict[str, Any]) -> str:
    order = ["Durbin-Watson", "ADF", "KPSS", "Breusch-Pagan", "White", "Cointegration"]
    marks = {"Pass": "P", "Fail": "F", "Watch": "W", "Unavailable": "?"}
    return "".join(marks.get(str(row.get(f"status__{t.replace(' ', '_')}")), "?") for t in order)


def _write_report(repo_root: Path, stream: str, round_n: int, round_dir: Path,
                  new_rows: List[Dict[str, Any]], all_rows: List[Dict[str, Any]]) -> None:
    finalist = finalist_reference(repo_root, stream)
    ranked = sorted(all_rows, key=candidate_sort_key)
    lines = [
        f"# Diagnostics Lab - {stream} - round {round_n}",
        "",
        f"Finalist reference: `{finalist['model']}` - paper horizon-mean MAPE "
        f"{finalist['paper_horizon_mean_mape']:.2f}% / annual {finalist['paper_annual_mape']:.2f}% - "
        f"core passes {finalist['core_passes']}/6 - Overall {finalist['overall']}.",
        "",
        f"New candidates this round: {len(new_rows)}; cumulative: {len(all_rows)}.",
        "",
        "Core-status key (DW/ADF/KPSS/BP/White/Coint): P=Pass F=Fail. JB is advisory.",
        "",
        "| # | model | arm | core | status | JB | DW | LB8 p | MAPE (paper) | vs finalist | annual | h1-4/5-8/9-12 |",
        "|---|-------|-----|------|--------|----|----|-------|--------------|-------------|--------|----------------|",
    ]
    for i, row in enumerate(ranked[:20], start=1):
        mape = row.get("paper_horizon_mean_mape")
        delta = (
            f"{float(mape) - finalist['paper_horizon_mean_mape']:+.2f}pp"
            if mape is not None and np.isfinite(float(mape))
            else "-"
        )
        def _num(value: Any, fmt: str) -> str:
            try:
                v = float(value)
                return format(v, fmt) if np.isfinite(v) else "-"
            except (TypeError, ValueError):
                return "-"

        lines.append(
            f"| {i} | `{row['model']}` | {row['arm']} | {row.get('core_passes', 0)}/6 | "
            f"{_status_compact(row)} | {str(row.get('status__Jarque-Bera', '?'))[:1]} | "
            f"{_num(row.get('stat__durbin_watson'), '.2f')} | {_num(row.get('stat__ljungbox_p_lag8'), '.3f')} | "
            f"{_fmt_mape(mape)} | {delta} | {_fmt_mape(row.get('paper_annual_mape'))} | "
            f"{_fmt_mape(row.get('mape_h01_04'))}/{_fmt_mape(row.get('mape_h05_08'))}/{_fmt_mape(row.get('mape_h09_12'))} |"
        )
    lines += ["", "## Arm summary", ""]
    arms: Dict[str, List[Dict[str, Any]]] = {}
    for row in all_rows:
        arms.setdefault(str(row["arm"]), []).append(row)
    for arm in sorted(arms):
        best = sorted(arms[arm], key=candidate_sort_key)[0]
        lines.append(
            f"- **{arm}** ({len(arms[arm])} configs): best {best.get('core_passes', 0)}/6 core "
            f"[{_status_compact(best)}] at {_fmt_mape(best.get('paper_horizon_mean_mape'))} - `{best['model']}`"
        )
    all_pass = [r for r in ranked if int(r.get("core_passes", 0)) == 6]
    lines += [
        "",
        "## Headline",
        "",
        (
            f"Best all-core-pass candidate: `{all_pass[0]['model']}` at "
            f"{_fmt_mape(all_pass[0].get('paper_horizon_mean_mape'))} "
            f"({float(all_pass[0]['paper_horizon_mean_mape']) - finalist['paper_horizon_mean_mape']:+.2f}pp vs finalist)."
            if all_pass
            else "No all-core-pass candidate yet."
        ),
    ]
    (round_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")

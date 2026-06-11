"""vNext pipeline governance tests.

These tests enforce the production-reproducibility contract:
- archived predictions must replay from saved fitted state (no silent drift);
- the deterministic refit recipe must reproduce archived predictions;
- streams without a parity-passing scorer must emit governed gaps, never
  fabricated numbers;
- forward scoring must be deterministic and must not run any model search.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VNEXT_STREAMS = ["HEAVY_RUC", "PED"]
TOL = 1e-6


def _state_dir(stream: str) -> Path:
    return REPO_ROOT / "data" / "dashboard_evidence_pack_reproducibility" / f"{stream.lower()}_vnext"


def _finalized(stream: str) -> bool:
    sdir = _state_dir(stream)
    return (sdir / "fitted_model_manifest.json").exists() and (
        sdir / "forward_scorer_parity_audit.json").exists()


@pytest.mark.parametrize("stream", VNEXT_STREAMS)
def test_history_actuals_match_governed_evidence(stream: str) -> None:
    """The canonical input history must agree exactly with evidence-pack actuals."""
    hist = pd.read_parquet(REPO_ROOT / "data" / "model_input_history" / f"{stream.lower()}_inputs.parquet")
    hist = hist.set_index("period")
    sp = pd.read_parquet(REPO_ROOT / "data" / "dashboard_evidence_pack" / "data" / "scorecard_predictions.parquet")
    fin = pd.read_parquet(REPO_ROOT / "data" / "dashboard_evidence_pack" / "data" / "finalists.parquet")
    current = str(fin[fin["stream"] == stream]["model"].iloc[0])
    sp = sp[(sp["stream"] == stream) & (sp["model"] == current)]
    actuals = sp.groupby("target_period")["actual"].first()
    target = pd.to_numeric(hist["target"], errors="coerce")
    common = [p for p in actuals.index if p in target.index]
    assert len(common) >= 100 or len(common) >= actuals.index.nunique()
    max_delta = max(abs(float(actuals[p]) - float(target[p])) for p in common)
    assert max_delta <= 1e-6, f"history/evidence actual mismatch: {max_delta}"


@pytest.mark.parametrize("stream", VNEXT_STREAMS)
def test_state_replay_parity(stream: str) -> None:
    """Saved per-origin estimators must replay archived predictions within 1e-6."""
    if not _finalized(stream):
        pytest.skip(f"{stream} vNext state not finalized")
    from pipeline.vnext_run import _parity_state_replay

    manifest = json.loads((_state_dir(stream) / "fitted_model_manifest.json").read_text(encoding="utf-8"))
    members = [m["component_model"] for m in manifest["members"]]
    delta = _parity_state_replay(stream, _state_dir(stream), members)
    assert delta <= TOL, f"{stream} state replay parity failed: {delta}"


@pytest.mark.parametrize("stream", VNEXT_STREAMS)
def test_recipe_replay_parity(stream: str) -> None:
    """The deterministic refit recipe must reproduce archived validation predictions."""
    if not _finalized(stream):
        pytest.skip(f"{stream} vNext state not finalized")
    from pipeline.vnext_core import backtest, load_stream_data
    from pipeline.vnext_run import _spec_by_name

    sdir = _state_dir(stream)
    manifest = json.loads((sdir / "fitted_model_manifest.json").read_text(encoding="utf-8"))
    archived = pd.read_parquet(sdir / "component_validation_predictions.parquet")
    sd = load_stream_data(REPO_ROOT, stream)
    # Cheapest member is sufficient as a continuous regression guard; the full
    # member set is verified by `pipeline.vnext_run finalize`.
    member = manifest["members"][0]
    spec = _spec_by_name(stream, member["component_model"])
    fresh = backtest(sd, spec).predictions
    arch = archived[archived["component_label"] == member["component_label"]]
    merged = arch.merge(fresh, on=["origin", "target_period"], suffixes=("_a", "_b"))
    assert len(merged) == len(arch)
    delta = float((merged["pred_a"] - merged["pred_b"]).abs().max())
    assert delta <= TOL, f"{stream} recipe replay parity failed: {delta}"


@pytest.mark.parametrize("stream", VNEXT_STREAMS)
def test_parity_audit_status_consistent(stream: str) -> None:
    if not _finalized(stream):
        pytest.skip(f"{stream} vNext state not finalized")
    audit = json.loads((_state_dir(stream) / "forward_scorer_parity_audit.json").read_text(encoding="utf-8"))
    assert audit["parity_tolerance"] == TOL
    if audit["parity_status"] == "passed":
        assert audit["state_replay_max_abs_delta"] <= TOL
        assert audit["recipe_replay_max_abs_delta"] <= TOL


@pytest.mark.parametrize("stream", VNEXT_STREAMS)
def test_no_fake_forecasts_on_gap(stream: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed parity gate must yield missing forecast values, never numbers."""
    from pipeline import vnext_forward

    if not _finalized(stream):
        pytest.skip(f"{stream} vNext state not finalized")
    scorer = vnext_forward.load_scorer(stream)
    assert scorer is not None
    # Force the runtime gate to fail.
    monkeypatch.setattr(scorer, "runtime_state_gate_delta", 1.0)
    assert not scorer.numeric_enabled
    from pipeline.vnext_core import load_stream_data

    sd = load_stream_data(REPO_ROOT, stream)
    periods = [sd.latest_actual + i + 1 for i in range(4)]
    assumptions = pd.DataFrame(index=pd.PeriodIndex(periods, freq="Q-DEC"))
    future, comp, capability = vnext_forward.forward_forecast(stream, assumptions, scorer)
    assert capability["capability_status"] == "parity_failed"
    assert not capability["forecast_capability_available"]
    assert future["forecast"].isna().all(), "gap rows must have missing forecasts"
    assert (~future["forecast_available"].astype(bool)).all()
    assert not (pd.to_numeric(future["forecast"], errors="coerce") == 0).any()


@pytest.mark.parametrize("stream", VNEXT_STREAMS)
def test_forward_scoring_runs_no_model_search(stream: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Scoring future rows must never invoke the candidate grid (broad search)."""
    if not _finalized(stream):
        pytest.skip(f"{stream} vNext state not finalized")
    import pipeline.vnext_candidates as vc
    from pipeline import vnext_forward
    from pipeline.vnext_core import load_stream_data

    def _boom(*args, **kwargs):  # pragma: no cover
        raise AssertionError("candidate_grid must not be called during forward scoring")

    monkeypatch.setattr(vc, "candidate_grid", _boom)
    scorer = vnext_forward.load_scorer(stream)
    if scorer is None or not scorer.numeric_enabled:
        pytest.skip(f"{stream} numeric scorer not enabled")
    sd = load_stream_data(REPO_ROOT, stream)
    assumptions = _synthetic_assumptions(stream, sd, horizon=4)
    future, comp, capability = vnext_forward.forward_forecast(stream, assumptions, scorer)
    assert capability["capability_status"] == "numeric_forecast_available"
    assert future["forecast"].notna().all()
    assert (pd.to_numeric(future["forecast"], errors="coerce") > 0).all()


@pytest.mark.parametrize("stream", VNEXT_STREAMS)
def test_forward_scoring_deterministic(stream: str) -> None:
    if not _finalized(stream):
        pytest.skip(f"{stream} vNext state not finalized")
    from pipeline import vnext_forward
    from pipeline.vnext_core import load_stream_data

    scorer = vnext_forward.load_scorer(stream)
    if scorer is None or not scorer.numeric_enabled:
        pytest.skip(f"{stream} numeric scorer not enabled")
    sd = load_stream_data(REPO_ROOT, stream)
    assumptions = _synthetic_assumptions(stream, sd, horizon=6)
    f1, _, _ = vnext_forward.forward_forecast(stream, assumptions, scorer)
    f2, _, _ = vnext_forward.forward_forecast(stream, assumptions, scorer)
    np.testing.assert_allclose(f1["forecast"].astype(float), f2["forecast"].astype(float), rtol=0, atol=0)


@pytest.mark.parametrize("stream", VNEXT_STREAMS)
def test_forecast_outputs_carry_governance_metadata(stream: str) -> None:
    if not _finalized(stream):
        pytest.skip(f"{stream} vNext state not finalized")
    sdir = _state_dir(stream)
    if not (sdir / "future_forecasts.parquet").exists():
        pytest.skip("evidence stage not yet run")
    future = pd.read_parquet(sdir / "future_forecasts.parquet")
    for col in ["scorer_version", "parity_status", "capability_status"]:
        assert col in future.columns, f"missing governance metadata column {col}"


def test_governed_evidence_pack_untouched_by_pipeline_outputs() -> None:
    """Pipeline outputs must live outside data/dashboard_evidence_pack."""
    pack = REPO_ROOT / "data" / "dashboard_evidence_pack"
    assert not (pack / "data" / "search_predictions.parquet").exists()
    assert not any(pack.glob("**/*vnext*"))


def _synthetic_assumptions(stream: str, sd, horizon: int) -> pd.DataFrame:
    """Flat-forward assumptions built from the last actual quarter's inputs."""
    from pipeline.vnext_forward import REQUIRED_USER_COLUMNS

    last = sd.history.loc[sd.latest_actual]
    periods = pd.PeriodIndex([sd.latest_actual + i + 1 for i in range(horizon)], freq="Q-DEC")
    data = {}
    for col in REQUIRED_USER_COLUMNS[stream]:
        data[col] = [float(last[col])] * horizon
    return pd.DataFrame(data, index=periods)

"""AR(1) engine: determinism, parity, winner equality, pack integrity."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline import vnext_core as vc
from pipeline.ar1_engine import (
    AR1_MODEL_NAME,
    capability_record,
    fit_production_state,
    load_state,
    repro_dir,
    state_replay_max_delta,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def state() -> dict:
    loaded = load_state(ROOT)
    assert loaded is not None, "run scripts/build_ar1_engine_state.py"
    return loaded


def test_refit_is_deterministic_and_matches_committed_state(state: dict) -> None:
    fresh = fit_production_state(ROOT)
    assert fresh["beta"] == pytest.approx(state["beta"], abs=1e-12)
    assert fresh["rho"] == pytest.approx(state["rho"], abs=1e-12)
    assert fresh["latest_actual"] == state["latest_actual"]
    assert fresh["input_history_sha256"] == state["input_history_sha256"]
    assert state_replay_max_delta(ROOT, state) <= vc.PARITY_TOLERANCE_ABS


def test_capability_gate_passes(state: dict) -> None:
    record = capability_record(ROOT)
    assert record["forecast_capability_available"] is True
    assert record["parity_status"] == "passed"
    assert record["model"] == AR1_MODEL_NAME


def test_state_hash_manifest_matches() -> None:
    manifest = json.loads((repro_dir(ROOT) / "fitted_model_manifest.json").read_text(encoding="utf-8"))
    assert manifest["finalist_model"] == AR1_MODEL_NAME
    assert manifest["engine"] == "ar1"
    assert manifest["members"][0]["component_weight"] == 1.0


def test_ar1_evidence_pack_finalist_matches_diaglab_winner() -> None:
    """The alternate evidence pack's PED finalist must reproduce the
    Diagnostics Lab winner: same paper-grid MAPE and an all-core-pass matrix."""
    data = ROOT / "data" / "engine_ar1" / "dashboard_evidence_pack" / "data"
    finalists = pd.read_parquet(data / "finalists.parquet")
    ped = finalists[finalists["stream"].astype(str).eq("PED")].iloc[0]
    assert str(ped["model"]) == AR1_MODEL_NAME
    assert float(ped["quarterly_mape"]) == pytest.approx(3.2233, abs=2e-3)
    matrix = pd.read_parquet(data / "diagnostic_pass_matrix.parquet")
    ped_matrix = matrix[matrix["stream"].astype(str).eq("PED")].set_index("diagnostic_test")["pass_status"]
    for test_name in ("Durbin-Watson", "ADF", "KPSS", "Breusch-Pagan", "White", "Cointegration"):
        assert str(ped_matrix.loc[test_name]) == "Pass", test_name
    assert str(ped_matrix.loc["Jarque-Bera"]) == "Watch"
    assert str(ped_matrix.loc["Overall"]) == "Watch"
    # Light and Heavy rows are byte-identical to the incumbent pack.
    incumbent = pd.read_parquet(ROOT / "data" / "dashboard_evidence_pack" / "data" / "diagnostic_pass_matrix.parquet")
    for stream in ("LIGHT_RUC", "HEAVY_RUC"):
        left = matrix[matrix["stream"].astype(str).eq(stream)].reset_index(drop=True)
        right = incumbent[incumbent["stream"].astype(str).eq(stream)].reset_index(drop=True)
        pd.testing.assert_frame_equal(left, right)


def test_ar1_scorecard_keys_identical_to_incumbent() -> None:
    """Template-merge guarantee: the AR(1) PED rows sit on exactly the
    incumbent finalist's (score_basis, origin, target_period) grid."""
    alt = pd.read_parquet(ROOT / "data" / "engine_ar1" / "dashboard_evidence_pack" / "data" / "scorecard_predictions.parquet")
    inc = pd.read_parquet(ROOT / "data" / "dashboard_evidence_pack" / "data" / "scorecard_predictions.parquet")
    key_cols = ["score_basis", "origin", "target_period"]
    alt_keys = alt[alt["stream"].eq("PED")][key_cols].sort_values(key_cols).reset_index(drop=True)
    inc_keys = inc[inc["stream"].eq("PED")][key_cols].sort_values(key_cols).reset_index(drop=True)
    pd.testing.assert_frame_equal(alt_keys, inc_keys)
    # The Schiff benchmark rows are deliberately untouched; the finalist is AR(1).
    non_schiff = alt[alt["stream"].eq("PED") & ~alt["model"].astype(str).str.contains("SCHIFF")]
    assert set(non_schiff["model"].astype(str)) == {AR1_MODEL_NAME}


def test_ar1_runtime_pack_loads_and_differs_only_where_expected() -> None:
    from model_dashboard.revenue_outlook import load_revenue_outlook_pack

    alt = load_revenue_outlook_pack(ROOT / "data" / "engine_ar1" / "current_revenue_outlook", repo_root=ROOT)
    inc = load_revenue_outlook_pack(ROOT / "data" / "current_revenue_outlook", repo_root=ROOT)
    assert alt is not None and inc is not None
    assert str(alt.manifest.get("engine")) == "ar1"

    def _trace(pack, series_label: str, trace: str) -> pd.Series:
        rows = pack.revenue_chart_rows
        label_col = "series_label" if "series_label" in rows.columns else "stream_label"
        sub = rows[
            rows["time_grain"].astype(str).eq("june_year")
            & rows[label_col].astype(str).eq(series_label)
            & rows["trace_name"].astype(str).eq(trace)
        ]
        return pd.Series(
            pd.to_numeric(sub["value"], errors="coerce").to_numpy(),
            index=pd.to_numeric(sub["june_year"], errors="coerce").to_numpy(),
        ).dropna().sort_index()

    # PED path differs (that's the engine change)...
    ped_alt = _trace(alt, "PED VKT per capita", "Current finalist Base case")
    ped_inc = _trace(inc, "PED VKT per capita", "Current finalist Base case")
    assert not np.allclose(ped_alt.loc[2030:], ped_inc.loc[2030:])
    # ... Heavy RUC is identical (fully independent of PED) ...
    heavy_alt = _trace(alt, "Heavy RUC net km", "Current finalist Base case")
    heavy_inc = _trace(inc, "Heavy RUC net km", "Current finalist Base case")
    pd.testing.assert_series_equal(heavy_alt, heavy_inc)
    # ... and the MBU26 official comparator is engine-invariant.
    mbu_alt = _trace(alt, "Total NLTF revenue", "MBU26 official")
    mbu_inc = _trace(inc, "Total NLTF revenue", "MBU26 official")
    pd.testing.assert_series_equal(mbu_alt, mbu_inc)

from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.benchmark_dashboard import benchmark_parquet_backend
from model_dashboard.data_loader import load_parquet_dashboard
from model_dashboard.plots import _competitive_landscape_subset, _sample_by_stream


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "mini_parquet"


def test_backend_benchmark_uses_parquet_fixture() -> None:
    result = benchmark_parquet_backend(FIXTURE_ROOT, Path(__file__).resolve().parents[1], repeats=1)
    labels = {item["label"] for item in result["benchmarks"]}

    assert result["source_mode"] == "parquet"
    assert result["data_root"].endswith("mini_parquet")
    assert "load_parquet_dashboard_uncached" in labels
    assert result["row_counts"]["summary"] > 0
    assert result["row_counts"]["recommended"] == 3


def test_parquet_fixture_loads_without_legacy_run_folder() -> None:
    loaded = load_parquet_dashboard(FIXTURE_ROOT, Path(__file__).resolve().parents[1])

    assert loaded.manifest is not None
    assert loaded.manifest["source_mode"] == "parquet"
    assert len(loaded.data["recommended"]) == 3
    assert len(loaded.data["schiff_df"]) == 3
    assert len(loaded.data["weights"]) == 8


def test_candidate_landscape_subset_preserves_governance_anchors() -> None:
    rows = []
    for stream in ["PED VKT per capita", "Light RUC volume", "Heavy RUC volume"]:
        for idx in range(250):
            rows.append(
                {
                    "stream_label": stream,
                    "quarterly_mape": float(idx + 1),
                    "annual_mape": float(250 - idx),
                    "is_finalist": idx == 249,
                    "is_schiff": idx == 248,
                }
            )
    frame = pd.DataFrame(rows)

    subset = _competitive_landscape_subset(frame, max_rows=120)

    assert len(subset) <= 120
    assert int(subset["is_finalist"].sum()) == 3
    assert int(subset["is_schiff"].sum()) == 3


def test_residual_scatter_sampling_is_bounded_and_stream_balanced() -> None:
    frame = pd.DataFrame(
        {
            "stream_label": ["PED VKT per capita"] * 10_000 + ["Light RUC volume"] * 10_000,
            "pred": range(20_000),
            "error_pct": range(20_000),
        }
    )

    sampled = _sample_by_stream(frame, max_rows=1200)

    assert len(sampled) == 1200
    assert sampled["stream_label"].value_counts().to_dict() == {
        "PED VKT per capita": 600,
        "Light RUC volume": 600,
    }

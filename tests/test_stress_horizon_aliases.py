from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from model_dashboard.data_loader import DEFAULT_EVIDENCE_PACK_ROOT, load_evidence_pack, resolve_evidence_pack_root
from model_dashboard.labels import STRESS_BUCKET_ORDER
from model_dashboard.plots import plot_stress_checks
from tests.fixtures.expected_values import EXPECTED_STRESS_MAPE


ROOT = Path(__file__).resolve().parents[1]


def test_stress_horizon_alias_coalescing() -> None:
    data_root = resolve_evidence_pack_root(os.environ.get("DASHBOARD_EVIDENCE_PACK_ROOT", str(DEFAULT_EVIDENCE_PACK_ROOT)))
    if not (Path(data_root) / "manifest.json").exists():
        pytest.skip("Stress horizon evidence-pack test requires DASHBOARD_EVIDENCE_PACK_ROOT or data/dashboard_evidence_pack.")
    loaded = load_evidence_pack(data_root, ROOT)
    stress = loaded.data["stress"].copy()
    stress["bucket"] = stress["stress_bucket"].astype(str)

    expected_order = ["1-4 qtrs", "5-8 qtrs", "9-12 qtrs", "2024+", "2022-23", "Annual"]
    assert list(STRESS_BUCKET_ORDER) == expected_order

    by_stream = {
        stream: frame.sort_values("stress_bucket")
        for stream, frame in stress.groupby("stream_label", sort=False, observed=False)
    }

    ped = by_stream["PED VKT per capita"]
    light = by_stream["Light RUC volume"]
    heavy = by_stream["Heavy RUC volume"]

    for frame in [ped, light, heavy]:
        assert list(frame["bucket"]) == expected_order

    values = stress.set_index(["stream_label", "bucket"])["mape"]
    for key, expected in EXPECTED_STRESS_MAPE.items():
        actual = values.loc[key]
        if pd.isna(expected):
            assert pd.isna(actual), f"{key} should remain a missing-value gap"
        else:
            assert float(actual) == pytest.approx(expected, abs=0.001)

    required_non_null = {
        "PED VKT per capita": ["1-4 qtrs", "5-8 qtrs", "9-12 qtrs", "2022-23", "Annual"],
        "Light RUC volume": ["1-4 qtrs", "5-8 qtrs", "9-12 qtrs", "2022-23", "Annual"],
        "Heavy RUC volume": ["1-4 qtrs", "5-8 qtrs", "9-12 qtrs", "2022-23", "Annual"],
    }
    for stream, buckets in required_non_null.items():
        for bucket in buckets:
            assert pd.notna(values.loc[(stream, bucket)]), f"{stream} is missing {bucket}"

    figure = plot_stress_checks(stress)
    assert list(figure.layout.xaxis.categoryarray) == expected_order
    for trace in figure.data:
        assert trace.connectgaps is False

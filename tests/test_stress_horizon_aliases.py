from __future__ import annotations

import math
import os
from pathlib import Path

import pandas as pd
import pytest

from model_dashboard.data_loader import DEFAULT_DIAGNOSTIC_AUDIT_ROOT, load_parquet_dashboard
from model_dashboard.labels import STRESS_BUCKET_ORDER
from model_dashboard.plots import plot_stress_checks


ROOT = Path(__file__).resolve().parents[1]


def _is_missing(value: object) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value)) or bool(pd.isna(value))


def test_stress_horizon_alias_coalescing() -> None:
    data_root = Path(os.environ.get("MODEL_DIAGNOSTIC_DATA_ROOT", DEFAULT_DIAGNOSTIC_AUDIT_ROOT)).expanduser()
    loaded = load_parquet_dashboard(data_root, ROOT, allow_csv_preview=False)
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

    required_ped_light = ["1-4 qtrs", "5-8 qtrs", "9-12 qtrs", "2024+", "2022-23", "Annual"]
    required_heavy = ["1-4 qtrs", "5-8 qtrs", "9-12 qtrs", "Annual"]

    for stream, frame, buckets in [
        ("PED VKT per capita", ped, required_ped_light),
        ("Light RUC volume", light, required_ped_light),
        ("Heavy RUC volume", heavy, required_heavy),
    ]:
        values = frame.set_index("bucket")["mape"]
        for bucket in buckets:
            assert pd.notna(values.loc[bucket]), f"{stream} is missing {bucket}"

    expected_values = {
        ("PED VKT per capita", "1-4 qtrs"): 1.56,
        ("PED VKT per capita", "5-8 qtrs"): 2.50,
        ("PED VKT per capita", "9-12 qtrs"): 3.52,
        ("PED VKT per capita", "2024+"): 0.96,
        ("PED VKT per capita", "2022-23"): 2.17,
        ("PED VKT per capita", "Annual"): 2.39,
        ("Light RUC volume", "1-4 qtrs"): 7.74,
        ("Light RUC volume", "5-8 qtrs"): 9.49,
        ("Light RUC volume", "9-12 qtrs"): 10.53,
        ("Light RUC volume", "2024+"): 6.25,
        ("Light RUC volume", "2022-23"): 18.79,
        ("Light RUC volume", "Annual"): 6.00,
        ("Heavy RUC volume", "1-4 qtrs"): 2.80,
        ("Heavy RUC volume", "5-8 qtrs"): 3.54,
        ("Heavy RUC volume", "9-12 qtrs"): 4.27,
        ("Heavy RUC volume", "Annual"): 3.02,
    }
    values = stress.set_index(["stream_label", "bucket"])["mape"]
    for key, expected in expected_values.items():
        assert float(values.loc[key]) == pytest.approx(expected, abs=0.02)

    heavy_values = heavy.set_index("bucket")["mape"]
    assert _is_missing(heavy_values.loc["2024+"])
    assert _is_missing(heavy_values.loc["2022-23"])

    figure = plot_stress_checks(stress)
    assert list(figure.layout.xaxis.categoryarray) == expected_order
    for trace in figure.data:
        assert trace.connectgaps is False
        if trace.name == "Heavy RUC volume":
            y_by_bucket = dict(zip(trace.x, trace.y))
            assert _is_missing(y_by_bucket["2024+"])
            assert _is_missing(y_by_bucket["2022-23"])

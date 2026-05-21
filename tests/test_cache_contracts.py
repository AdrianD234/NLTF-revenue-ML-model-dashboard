from __future__ import annotations

from pathlib import Path

import pandas as pd

import app
from model_dashboard.data_loader import run_signature


def test_run_signature_tracks_file_size_and_mtime(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_20260520_000000"
    run_dir.mkdir()
    target = run_dir / "final_summary.csv"
    pd.DataFrame([{"stage": "final", "stream": "PED"}]).to_csv(target, index=False)

    first = run_signature(run_dir)
    pd.DataFrame([{"stage": "final", "stream": "PED"}, {"stage": "final", "stream": "HEAVY_RUC"}]).to_csv(target, index=False)
    second = run_signature(run_dir)

    assert first != second
    assert first[0][0] == "final_summary.csv"
    assert len(first[0]) == 3


def test_run_signature_ignores_directories(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_20260520_000000"
    run_dir.mkdir()
    (run_dir / "nested").mkdir()
    (run_dir / "final_summary.csv").write_text("stage\nfinal\n", encoding="utf-8")

    signature = run_signature(run_dir)

    assert len(signature) == 1
    assert signature[0][0] == "final_summary.csv"


def test_cached_discover_run_folders_reuses_same_parent_signature(tmp_path: Path, monkeypatch) -> None:
    parent = tmp_path / "runs"
    run_dir = parent / "run_20260520_000000"
    run_dir.mkdir(parents=True)
    (run_dir / "final_summary.csv").write_text("stage\nfinal\n", encoding="utf-8")

    calls = {"count": 0}

    def fake_discover(path: Path, ignored: set[str]) -> list[Path]:
        calls["count"] += 1
        assert ignored == {"run_ignored"}
        return [path / "run_20260520_000000"]

    monkeypatch.setattr(app, "discover_run_folders", fake_discover)
    app.cached_discover_run_folders.clear()
    signature = app.directory_signature(parent)

    first = app.cached_discover_run_folders(str(parent), ("run_ignored",), signature)
    second = app.cached_discover_run_folders(str(parent), ("run_ignored",), signature)

    assert first == second
    assert calls["count"] == 1

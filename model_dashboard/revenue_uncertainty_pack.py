"""Runtime lookup for the materialised uncertainty pack.

The Streamlit runtime must never run the simulation. Everything expensive -
10 000 draws, the copula, the formula propagation - happens offline in
``scripts/build_revenue_outlook_uncertainty_pack.py``.  At render time this
module does one parquet read (cached for the process) and one filter.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

__all__ = [
    "UNCERTAINTY_PACK_DIR",
    "UncertaintyPack",
    "band_rows_for_series",
    "load_uncertainty_pack",
]

UNCERTAINTY_PACK_DIR = Path("data") / "revenue_outlook_uncertainty"


class UncertaintyPack:
    """Band rows plus the manifest that says how they were made."""

    def __init__(self, band_rows: pd.DataFrame, manifest: dict, basis: pd.DataFrame) -> None:
        self.band_rows = band_rows
        self.manifest = manifest
        self.basis = basis

    @property
    def available(self) -> bool:
        return not self.band_rows.empty

    def series_ids(self) -> set[str]:
        if self.band_rows.empty:
            return set()
        return set(self.band_rows["series_id"].astype(str))


def load_uncertainty_pack(repo_root: Path | str | None = None) -> UncertaintyPack:
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    directory = root / UNCERTAINTY_PACK_DIR
    rows_path = directory / "uncertainty_band_rows.parquet"
    if not rows_path.exists():
        return UncertaintyPack(pd.DataFrame(), {}, pd.DataFrame())
    band_rows = pd.read_parquet(rows_path)
    manifest_path = directory / "manifest.json"
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    )
    basis_path = directory / "june_year_basis.parquet"
    basis = pd.read_parquet(basis_path) if basis_path.exists() else pd.DataFrame()
    return UncertaintyPack(band_rows, manifest, basis)


def band_rows_for_series(pack: UncertaintyPack, series_id: str) -> pd.DataFrame:
    """The FY-ordered band rows for one series. A pure filter - no computation."""
    if pack is None or pack.band_rows.empty or not series_id:
        return pd.DataFrame()
    selected = pack.band_rows[pack.band_rows["series_id"].astype(str).eq(str(series_id))]
    if selected.empty:
        return selected
    return selected.sort_values("FY").reset_index(drop=True)

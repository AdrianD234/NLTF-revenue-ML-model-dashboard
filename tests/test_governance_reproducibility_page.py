from __future__ import annotations

from pathlib import Path
import hashlib

from app import (
    REPRODUCIBILITY_PAGE,
    SOURCE_WORKBOOK_MANIFEST_PATH,
    reproducibility_build_flow_table,
    reproducibility_glossary_table,
    source_workbook_manifest,
    _pack_zip_bytes,
)
from model_dashboard.light_ruc_reproducibility import (
    load_reproducibility_pack,
    reproducibility_stream_labels,
)


ROOT = Path(__file__).resolve().parents[1]


def test_governance_reproducibility_page_uses_generic_stream_selector_content() -> None:
    assert REPRODUCIBILITY_PAGE == "Governance & Reproducibility"
    streams = set(reproducibility_stream_labels())
    assert streams == {"PED VKT per capita", "Light RUC volume", "Heavy RUC volume"}

    flow = reproducibility_build_flow_table("All streams")
    assert streams.issubset(set(flow["Stream"]))
    assert "exp(base log prediction + residual log prediction)" in flow["Evidence"].astype(str).str.cat(sep=" | ")
    assert "Weighted component contributions sum" in flow["Evidence"].astype(str).str.cat(sep=" | ")
    assert "stored component prediction" in flow["Evidence"].astype(str).str.cat(sep=" | ")

    glossary = reproducibility_glossary_table()
    assert {"Replay pack", "Component trace", "Chart-source isolation"}.issubset(set(glossary["Term"]))


def test_source_workbook_manifest_is_written_without_requiring_repo_workbook_copy() -> None:
    manifest = source_workbook_manifest()
    path = ROOT / SOURCE_WORKBOOK_MANIFEST_PATH

    assert path.exists()
    assert "status" in manifest
    assert "repo_path" in manifest
    assert "candidate_paths" in manifest
    assert "configured_env_var" in manifest
    if manifest.get("available"):
        assert manifest.get("sha256")
        assert manifest.get("filename") == "Master Copy revenue modelling workbook.xlsx"


def test_reproducibility_page_helpers_do_not_alter_main_chart_sources() -> None:
    before = _chart_source_hashes()
    assert before

    for stream in reproducibility_stream_labels():
        pack = load_reproducibility_pack(stream)
        assert pack.available
        archive = _pack_zip_bytes(pack)
        assert len(archive) > 1_000

    _ = source_workbook_manifest()
    after = _chart_source_hashes()
    assert after == before


def _chart_source_hashes() -> dict[str, str]:
    source_dir = ROOT / "artifacts" / "chart_sources"
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(source_dir.glob("*.csv"))
    }

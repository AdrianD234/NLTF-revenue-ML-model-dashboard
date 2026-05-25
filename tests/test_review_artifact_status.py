from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_governance_docs_exist_for_repo_cleanup_contract() -> None:
    for name in ["ARCHITECTURE.md", "DATA_CONTRACT.md", "GOVERNANCE_RULES.md"]:
        path = ROOT / "docs" / name
        assert path.exists(), f"Missing governance doc: {name}"
        assert len(path.read_text(encoding="utf-8")) > 500


def test_readme_describes_parquet_first_runtime() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "default data source is the curated Parquet dashboard pack" in text
    assert "Legacy run-folder CSV/XLSX outputs are retained only for review" in text
    assert "DASHBOARD_EVIDENCE_PACK_ROOT" in text
    assert "STAGE1_DASHBOARD_EVIDENCE_PACK_ROOT" in text
    assert "MODEL_DIAGNOSTIC_DATA_ROOT" in text
    assert text.index("DASHBOARD_EVIDENCE_PACK_ROOT") < text.index("MODEL_DIAGNOSTIC_DATA_ROOT")
    assert ("MODEL" + "_RUN_DIR") not in text


def test_agent_instructions_use_parquet_data_quality_rule() -> None:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "Parquet data-quality rule" in text
    assert "Legacy run-folder CSV/XLSX outputs are review-only" in text
    assert ("stage1_finalist" + "_arbitration_outputs") not in text

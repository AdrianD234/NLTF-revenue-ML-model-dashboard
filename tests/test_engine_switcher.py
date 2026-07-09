"""Engine switcher: default, page sweep under both engines, flip consistency."""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import app
from model_dashboard.engine import (
    ENGINE_AR1,
    ENGINE_ENSEMBLE,
    ENGINE_KEY,
    engine_default,
    engine_evidence_root,
    engine_repro_pack_dirs,
    engine_revenue_outlook_dir,
)

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = str(ROOT / "app.py")
PAGES = [
    "Overview",
    "Diagnostics",
    "Scenario Comparison",
    app.REVENUE_OUTLOOK_PAGE,
]


def test_default_engine_is_ar1(monkeypatch) -> None:
    monkeypatch.delenv("DASHBOARD_ENGINE_DEFAULT", raising=False)
    assert engine_default() == ENGINE_AR1
    monkeypatch.setenv("DASHBOARD_ENGINE_DEFAULT", "ensemble")
    assert engine_default() == ENGINE_ENSEMBLE
    monkeypatch.setenv("DASHBOARD_ENGINE_DEFAULT", "nonsense")
    assert engine_default() == ENGINE_AR1


def test_engine_path_resolvers() -> None:
    assert engine_evidence_root(ENGINE_AR1).as_posix().endswith("data/engine_ar1/dashboard_evidence_pack")
    assert engine_evidence_root(ENGINE_ENSEMBLE).as_posix().endswith("data/dashboard_evidence_pack")
    assert engine_revenue_outlook_dir(ENGINE_AR1).as_posix() == "data/engine_ar1/current_revenue_outlook"
    assert engine_revenue_outlook_dir(ENGINE_ENSEMBLE).as_posix() == "data/current_revenue_outlook"
    assert engine_repro_pack_dirs(ENGINE_AR1)["PED"] == "ped_ar1"
    assert engine_repro_pack_dirs(ENGINE_ENSEMBLE)["PED"] == "ped_vnext"
    assert engine_repro_pack_dirs(ENGINE_AR1)["LIGHT_RUC"] == engine_repro_pack_dirs(ENGINE_ENSEMBLE)["LIGHT_RUC"]


def _boot(engine: str) -> AppTest:
    at = AppTest.from_file(APP_PATH, default_timeout=180)
    at.session_state[ENGINE_KEY] = engine
    at.run()
    assert not at.exception
    return at


@pytest.mark.parametrize("engine", [ENGINE_AR1, ENGINE_ENSEMBLE])
@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_under_both_engines(engine: str, page: str) -> None:
    at = _boot(engine)
    at.radio[0].set_value(page)
    at.run()
    assert not at.exception, f"{page} raised under engine={engine}"


def test_engine_flip_moves_every_executive_surface_together() -> None:
    at = _boot(ENGINE_AR1)
    rendered_ar1 = "\n".join(str(m.value) for m in at.markdown)
    assert "PED AR(1) model" in rendered_ar1
    assert "3.22%" in rendered_ar1

    at.session_state[ENGINE_KEY] = ENGINE_ENSEMBLE
    at.run()
    assert not at.exception
    rendered_ens = "\n".join(str(m.value) for m in at.markdown)
    assert "PED weighted ensemble (vNext)" in rendered_ens
    assert "3.13%" in rendered_ens
    assert "PED AR(1) model" not in rendered_ens


def test_diagnostic_matrix_follows_engine() -> None:
    at = _boot(ENGINE_AR1)
    at.radio[0].set_value("Diagnostics")
    at.run()
    rendered = "\n".join(str(m.value) for m in at.markdown)
    # AR(1) engine: every core test passes for every stream - the matrix
    # carries no Fail cell at all (PED is Overall Watch via advisory JB).
    assert ">Fail<" not in rendered

    at.session_state[ENGINE_KEY] = ENGINE_ENSEMBLE
    at.run()
    assert not at.exception
    rendered = "\n".join(str(m.value) for m in at.markdown)
    # Incumbent engine: the PED Durbin-Watson/White failures reappear.
    assert ">Fail<" in rendered

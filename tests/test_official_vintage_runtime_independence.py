"""Static gates keeping generic runtime code free of MBU26-specific coupling.

The official-vintage framework exists so a future BEFU/PREFU/MBU release needs
only a registry entry and one materialisation command. That guarantee erodes
the moment new runtime code reaches for an MBU26-specific constant instead of
the registry. These tests draw the line explicitly.

MBU26 remains a first-class registered vintage: the legacy spine module, its
materializer, its compatibility adapters and MBU-specific source metadata are
all still allowed to name it. What is banned is NEW generic-runtime code
depending on the MBU26 pack directory, sheet name or release-round constants.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

BANNED_CONSTANTS = ("MBU26_SOURCE_PACK_DIR", "MBU26_SHEET_NAME", "MBU26_RELEASE_ROUND")

# Modules permitted to name the MBU26-specific constants:
#   - the legacy spine itself defines them
#   - the legacy materializer CLI is MBU26-specific by construction
#   - revenue_outlook keeps compatibility adapters over the frozen MBU26 pack
ALLOWED_CONSTANT_FILES = {
    "model_dashboard/mbu26_source_spine.py",
    "scripts/materialize_mbu26_annual_spine.py",
    "model_dashboard/revenue_outlook.py",
}

# Generic runtime modules that must resolve vintages through the registry.
GENERIC_RUNTIME_FILES = (
    "model_dashboard/official_vintage.py",
    "model_dashboard/fleet_mix.py",
    "model_dashboard/completeness_contract.py",
    "scripts/materialize_official_vintage.py",
    "scripts/build_official_vintage_reconciliation.py",
)

LEGACY_PACK_PATH_FRAGMENT = "revenue_model_source_pack/mbu26_annual_spine"


def _python_sources() -> list[Path]:
    paths: list[Path] = [ROOT / "app.py"]
    for directory in ("model_dashboard", "scripts", "pipeline", "config"):
        base = ROOT / directory
        if base.exists():
            paths.extend(
                path
                for path in base.rglob("*.py")
                if "__pycache__" not in path.parts
            )
    return sorted(paths)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


@pytest.mark.parametrize("constant", BANNED_CONSTANTS)
def test_no_new_runtime_dependency_on_mbu26_constants(constant: str) -> None:
    offenders = [
        _rel(path)
        for path in _python_sources()
        if _rel(path) not in ALLOWED_CONSTANT_FILES
        and constant in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], (
        f"{constant} is MBU26-specific; new runtime code must resolve the vintage "
        "through the official-vintage registry (load_official_vintage / "
        "default_bridge_vintage_id / default_comparator_vintage_id) instead. "
        f"Offending files: {offenders}"
    )


@pytest.mark.parametrize("module", GENERIC_RUNTIME_FILES)
def test_generic_runtime_modules_are_vintage_agnostic(module: str) -> None:
    source = (ROOT / module).read_text(encoding="utf-8")
    for constant in BANNED_CONSTANTS:
        assert constant not in source, f"{module} must not depend on {constant}"
    assert LEGACY_PACK_PATH_FRAGMENT not in source, (
        f"{module} hard-codes the legacy MBU26 pack path; reach it through the "
        "registry entry's source_pack_path instead"
    )


def test_generic_runtime_modules_do_not_import_from_the_legacy_spine_by_default() -> None:
    """The one permitted import is the governed formula registry.

    ``FORMULA_DEFINITIONS`` is documented as the dashboard formula authority
    and is shared by every vintage, so importing it is correct. Any other
    symbol pulled from the MBU26 spine into the generic loader would re-couple
    the framework to a single release.
    """
    source = (ROOT / "model_dashboard" / "official_vintage.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("mbu26_source_spine"):
            imported.update(alias.name for alias in node.names)
    assert imported <= {
        "FORMULA_DEFINITIONS",
        "DISPLAY_SERIES_METADATA",
        "REVENUE_PARTIAL_ACTUAL_FY",
    }, (
        "official_vintage.py may only borrow the governed formula registry and "
        f"display metadata from the legacy spine; found {sorted(imported)}"
    )


def test_registry_is_the_single_source_of_default_vintage_roles() -> None:
    """No module may hard-code which vintage is the default for either role."""
    banned_assignments = (
        'official_comparator_vintage_id = "MBU26"',
        "official_comparator_vintage_id = 'MBU26'",
        'bridge_assumption_vintage_id = "MBU26"',
        "bridge_assumption_vintage_id = 'MBU26'",
    )
    offenders = [
        _rel(path)
        for path in _python_sources()
        if any(text in path.read_text(encoding="utf-8") for text in banned_assignments)
    ]
    assert offenders == [], (
        "default vintage roles come from the registry flags is_default_comparator "
        f"and is_default_bridge_vintage, not from code. Offending files: {offenders}"
    )

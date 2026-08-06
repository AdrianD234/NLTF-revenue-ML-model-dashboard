from __future__ import annotations

from pathlib import Path

from .config import DEFAULT_DIAGNOSTIC_AUDIT_ROOT, DEFAULT_INFORMATION_PACK_ROOT


IGNORED_RECURSIVE_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".streamlit",
    ".venv",
    "__pycache__",
    "artifacts",
    "test-output",
}


def candidate_search_roots(data_root: str | Path, repo_root: str | Path | None = None) -> list[Path]:
    """Return ordered roots for a governed data pack lookup.

    The requested root is always first. Known adjacent pack names are inferred
    from the supplied root instead of hard-coding a user-specific filesystem.
    """

    requested = Path(data_root).expanduser()
    candidates: list[Path] = [requested]

    if requested.name.lower() == "model_diagnostic_audit_pack":
        candidates.append(requested.parent / "information pack")
    elif requested.name.lower() == "information pack":
        candidates.append(requested.parent / "model_diagnostic_audit_pack")

    candidates.extend([DEFAULT_INFORMATION_PACK_ROOT, DEFAULT_DIAGNOSTIC_AUDIT_ROOT])
    if repo_root is not None:
        repo_path = Path(repo_root).expanduser()
        repo_data = repo_path / "data"
        candidates.append(repo_data)
        mini_fixture = repo_path / "tests" / "fixtures" / "mini_parquet"
        requested_is_repo_default = requested == repo_data or str(requested).lower() in {"data", ".\\data"}
        requested_is_mini_fixture = requested.name.lower() == "mini_parquet"
        if requested_is_mini_fixture or requested_is_repo_default or not requested.exists():
            candidates.append(mini_fixture)

    roots: list[Path] = []
    seen: set[str] = set()
    for root in candidates:
        key = str(root.resolve() if root.exists() else root).lower()
        if key not in seen:
            roots.append(root)
            seen.add(key)
    return roots


def locate_dashboard_file(filename: str, roots: list[Path] | tuple[Path, ...]) -> Path | None:
    for root in roots:
        if not root.exists():
            continue
        direct = root / filename
        if direct.exists():
            return direct
        matches = sorted(
            (path for path in root.rglob(filename) if not _is_ignored_generated_path(path)),
            key=lambda path: (len(path.parts), str(path).lower()),
        )
        if matches:
            return matches[0]
    return None


def _is_ignored_generated_path(path: Path) -> bool:
    return any(part.lower() in IGNORED_RECURSIVE_DIRS for part in path.parts)

from __future__ import annotations

from pathlib import Path

from .config import DEFAULT_DIAGNOSTIC_AUDIT_ROOT, DEFAULT_INFORMATION_PACK_ROOT


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
        candidates.extend([repo_path, repo_path / "data", repo_path / "tests" / "fixtures" / "mini_parquet"])

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
        matches = sorted(root.rglob(filename), key=lambda path: (len(path.parts), str(path).lower()))
        if matches:
            return matches[0]
    return None

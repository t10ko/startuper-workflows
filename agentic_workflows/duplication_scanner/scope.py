from __future__ import annotations

from pathlib import Path

_PYTHON_SUFFIXES = frozenset({".py"})
_TS_SUFFIXES = frozenset({".ts", ".tsx"})
_SUPPORTED_SUFFIX_FAMILIES = (_PYTHON_SUFFIXES, _TS_SUFFIXES)
DEFAULT_MAX_SIBLINGS_PER_DIRECTORY = 5


def _suffix_family(suffix: str) -> frozenset[str] | None:
    for family in _SUPPORTED_SUFFIX_FAMILIES:
        if suffix in family:
            return family
    return None


def _same_directory_siblings(
    touched_path: Path,
    already_included: set[Path],
    *,
    max_siblings: int,
) -> list[Path]:
    family = _suffix_family(touched_path.suffix)
    if family is None or not touched_path.parent.is_dir():
        return []
    candidates = [
        sibling
        for sibling in touched_path.parent.iterdir()
        if sibling.is_file()
        and sibling.suffix in family
        and sibling not in already_included
    ]
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[:max_siblings]


def bounded_scan_paths(
    project_root: Path,
    touched_paths: list[Path],
    *,
    max_siblings_per_directory: int = DEFAULT_MAX_SIBLINGS_PER_DIRECTORY,
) -> list[Path]:
    """REQ-007: touched paths plus up to `max_siblings_per_directory`
    most-recently-modified same-directory, same-language-family siblings
    that are not themselves touched by the diff. Bounded, not whole-repo
    and not touched-only -- a token scanner can only find duplication
    among files it is actually given, so touched-files-only would make
    this dimension structurally unable to catch duplication against
    pre-existing, untouched code (the exact scenario it exists to catch).

    Returns absolute, resolved, deduplicated, deterministically sorted
    paths. `project_root` is resolved once up front so callers on a
    filesystem with a symlinked temp root (e.g. macOS `/tmp` ->
    `/private/tmp`) never hit a `relative_to()` mismatch downstream.
    """
    resolved_root = project_root.resolve()
    resolved_touched = {
        (path if path.is_absolute() else resolved_root / path).resolve()
        for path in touched_paths
    }
    scan_paths = set(resolved_touched)
    for touched_path in resolved_touched:
        siblings = _same_directory_siblings(
            touched_path,
            resolved_touched,
            max_siblings=max_siblings_per_directory,
        )
        scan_paths.update(siblings)
    return sorted(scan_paths, key=lambda path: path.as_posix())

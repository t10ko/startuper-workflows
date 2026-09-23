"""Small stdlib atomic-file helpers shared by the ledger-owning modules."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4


def ensure_parent_dir(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_text_atomic(
    path: Path,
    content: str,
    *,
    encoding: str = "utf-8",
) -> Path:
    """Write text to `path` using a sibling temporary file and atomic replace."""
    target = ensure_parent_dir(path)
    tmp_path = target.parent / f".{target.name}.{uuid4().hex}.tmp"
    try:
        tmp_path.write_text(content, encoding=encoding)
        tmp_path.replace(target)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    return target


def write_bytes_atomic(path: Path, content: bytes) -> Path:
    """Write bytes to `path` using a sibling temporary file and atomic replace."""
    target = ensure_parent_dir(path)
    tmp_path = target.parent / f".{target.name}.{uuid4().hex}.tmp"
    try:
        tmp_path.write_bytes(content)
        tmp_path.replace(target)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    return target

from __future__ import annotations

import json as project_json
from dataclasses import dataclass
from pathlib import Path

from .models import DuplicateCandidate, DuplicateOccurrence


@dataclass(frozen=True)
class _JscpdLoc:
    line: int


@dataclass(frozen=True)
class _JscpdFileRef:
    name: str
    startLoc: _JscpdLoc
    endLoc: _JscpdLoc


@dataclass(frozen=True)
class _JscpdDuplicateEntry:
    format: str = "unknown"
    lines: int = 0
    tokens: int = 0
    fragment: str = ""
    firstFile: _JscpdFileRef = None  # type: ignore[assignment]
    secondFile: _JscpdFileRef = None  # type: ignore[assignment]


@dataclass(frozen=True)
class _JscpdReport:
    duplicates: list[_JscpdDuplicateEntry]


def _loc(payload: object) -> _JscpdLoc:
    if not isinstance(payload, dict) or not isinstance(payload.get("line"), int):
        raise ValueError(f"jscpd loc must be {{'line': int}}, got {payload!r}")
    return _JscpdLoc(line=payload["line"])


def _file_ref(payload: object) -> _JscpdFileRef:
    if not isinstance(payload, dict) or not isinstance(payload.get("name"), str):
        raise ValueError(f"jscpd file ref must carry a string 'name', got {payload!r}")
    return _JscpdFileRef(
        name=payload["name"],
        startLoc=_loc(payload.get("startLoc")),
        endLoc=_loc(payload.get("endLoc")),
    )


def _entry(payload: object) -> _JscpdDuplicateEntry:
    if not isinstance(payload, dict):
        raise ValueError("jscpd duplicate entry must be a JSON object")
    return _JscpdDuplicateEntry(
        format=payload.get("format", "unknown"),
        lines=payload.get("lines", 0),
        tokens=payload.get("tokens", 0),
        fragment=payload.get("fragment", ""),
        firstFile=_file_ref(payload.get("firstFile")),
        secondFile=_file_ref(payload.get("secondFile")),
    )


def _report(payload: object) -> _JscpdReport:
    if not isinstance(payload, dict):
        raise ValueError("jscpd report must be a JSON object")
    raw_duplicates = payload.get("duplicates", [])
    if not isinstance(raw_duplicates, list):
        raise ValueError("jscpd report 'duplicates' must be a list")
    return _JscpdReport(duplicates=[_entry(entry) for entry in raw_duplicates])


def _relative_occurrence(
    file_ref: _JscpdFileRef,
    resolved_root: Path,
) -> DuplicateOccurrence:
    raw_path = Path(file_ref.name)
    if raw_path.is_absolute() and raw_path.is_relative_to(resolved_root):
        raw_path = raw_path.relative_to(resolved_root)
    return DuplicateOccurrence(
        path=raw_path,
        start_line=file_ref.startLoc.line,
        end_line=file_ref.endLoc.line,
    )


def parse_jscpd_report(
    report_path: Path,
    project_root: Path,
) -> list[DuplicateCandidate]:
    """Parse jscpd's JSON report into stable-ID DuplicateCandidate rows.
    One DuplicateCandidate per raw jscpd `duplicates[]` pair entry. jscpd's
    own pairwise-reporting quirk (3+ occurrences of one block reported as
    separate pairs) is intentionally left unmerged here -- that merge belongs
    to the D-C LLM classifier, not this deterministic parser."""
    raw_report = _report(
        project_json.loads(report_path.read_text(encoding="utf-8"))
    )
    resolved_root = project_root.resolve()

    ordered_entries = sorted(
        raw_report.duplicates,
        key=lambda entry: (
            entry.firstFile.name,
            entry.firstFile.startLoc.line,
            entry.secondFile.name,
            entry.secondFile.startLoc.line,
        ),
    )

    return [
        DuplicateCandidate(
            candidate_id=f"DUP-{index:03d}",
            format=entry.format,
            lines=entry.lines,
            tokens=entry.tokens,
            fragment=entry.fragment,
            first=_relative_occurrence(entry.firstFile, resolved_root),
            second=_relative_occurrence(entry.secondFile, resolved_root),
        )
        for index, entry in enumerate(ordered_entries, start=1)
    ]

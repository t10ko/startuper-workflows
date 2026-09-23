from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentic_workflows.types import JSONDict


@dataclass(frozen=True, slots=True)
class DuplicateOccurrence:
    path: Path
    start_line: int
    end_line: int

    def as_dict(self) -> JSONDict:
        return {
            "path": self.path.as_posix(),
            "start_line": self.start_line,
            "end_line": self.end_line,
        }


@dataclass(frozen=True, slots=True)
class DuplicateCandidate:
    candidate_id: str
    format: str
    lines: int
    tokens: int
    fragment: str
    first: DuplicateOccurrence
    second: DuplicateOccurrence

    def as_dict(self) -> JSONDict:
        return {
            "candidate_id": self.candidate_id,
            "format": self.format,
            "lines": self.lines,
            "tokens": self.tokens,
            "fragment": self.fragment,
            "first": self.first.as_dict(),
            "second": self.second.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class DuplicationReport:
    scope: str
    scanned_paths: list[Path]
    candidates: list[DuplicateCandidate]
    skipped_reason: str | None = None

"""Observational record of which instruction files actually load, and why.

Rules deferral questions (which globs actually fire, which rules are dead
weight) have only ever been argued. Each `InstructionsLoaded` event names one
instruction file and the reason it loaded (`session_start`, `nested_traversal`,
`path_glob_match`, `include`, or `compact`), which turns the argument into a
count.

Stated limit: `InstructionsLoaded` is observational only -- no output fields,
exit code ignored. This CANNOT filter or block a rule from loading. It is the
measuring instrument for the rules-payload lever, not an implementation of it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from agentic_workflows.time import utc_now


@dataclass(frozen=True)
class InstructionsLoadedRecord:
    """One `InstructionsLoaded` event as logged.

    `raw` carries the verbatim payload alongside the three extracted fields
    rather than instead of them. The field names this hook reads belong to
    Claude Code, not to this repo: if one is renamed upstream, extraction
    starts returning None and every later row would look empty while the log
    itself still looked healthy. Keeping the payload makes that recoverable
    after the fact instead of silently unmeasurable.
    """

    recorded_at: datetime
    file_path: str | None = None
    load_reason: str | None = None
    session_id: str | None = None
    raw: str = ""  # required payload; default only to keep field ordering

    def __post_init__(self) -> None:
        if not isinstance(self.raw, str) or not self.raw:
            raise ValueError("raw must be a non-empty string")

    def to_dict(self) -> dict[str, str | None]:
        return {
            "recorded_at": self.recorded_at.isoformat(),
            "file_path": self.file_path,
            "load_reason": self.load_reason,
            "session_id": self.session_id,
            "raw": self.raw,
        }


def _text_field(payload: dict[str, object], key: str) -> str | None:
    """One string field, or None when absent or not a string."""
    value = payload.get(key)
    return value if isinstance(value, str) else None


def build_instructions_loaded_record(raw_line: str) -> InstructionsLoadedRecord | None:
    """Decode one hook payload into a record, or None when it is unusable.

    Returns None rather than raising for every malformed input. This runs as a
    hook on a live session: a crash here would surface as harness noise on a
    path that exists only to measure, and a measurement is never worth
    interrupting the work it measures.
    """
    stripped = raw_line.strip()
    if not stripped:
        return None
    try:
        payload = json.loads(stripped)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    return InstructionsLoadedRecord(
        recorded_at=utc_now(),
        file_path=_text_field(payload, "file_path"),
        load_reason=_text_field(payload, "load_reason"),
        session_id=_text_field(payload, "session_id"),
        raw=stripped,
    )


def append_instructions_loaded_record(
    record: InstructionsLoadedRecord, log_path: Path
) -> None:
    """Append one record as a JSONL line, creating the log's directory."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{json.dumps(record.to_dict())}\n")


def read_instructions_loaded_records(
    log_path: Path,
) -> tuple[InstructionsLoadedRecord, ...]:
    """Every readable record in the log.

    A missing log is empty, not an error -- the hook may simply not have fired
    yet. An unreadable line is skipped rather than aborting the read: this log
    is appended to by a live hook, so a torn final write is expected and must
    not discard every record before it.
    """
    if not log_path.is_file():
        return ()
    records: list[InstructionsLoadedRecord] = []
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
            if not isinstance(payload, dict):
                continue
            raw = payload.get("raw")
            recorded_at = payload.get("recorded_at")
            if not isinstance(raw, str) or not isinstance(recorded_at, str):
                continue
            records.append(
                InstructionsLoadedRecord(
                    recorded_at=datetime.fromisoformat(recorded_at),
                    file_path=_text_field(payload, "file_path"),
                    load_reason=_text_field(payload, "load_reason"),
                    session_id=_text_field(payload, "session_id"),
                    raw=raw,
                )
            )
        except ValueError:
            continue
    return tuple(records)

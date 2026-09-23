"""Manage the ignored detailed-plan history log with deterministic pruning."""

# --- standalone bootstrap -------------------------------------------------
# This script may run from a consumer repo via symlink; resolve its real
# location and put both the runtime root and the sibling-script directory on
# sys.path before any agentic_workflows/sibling imports run.
def _bootstrap() -> None:
    import sys as _sys
    from pathlib import Path as _Path
    here = _Path(__file__).resolve().parent
    for candidate in (here, *here.parents):
        if (candidate / "agentic_workflows" / "__init__.py").is_file():
            _sys.path.insert(0, str(candidate))
            break
    if str(here) not in _sys.path:
        _sys.path.insert(0, str(here))


_bootstrap()
# --------------------------------------------------------------------------


import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from agentic_workflows.time import utc_now

HISTORY_PATH = Path("logs/detailed-plan-history.md")
HISTORY_TITLE = "# Detailed Plan History"
MAX_ENTRIES = 20
VALID_STATUSES = ("planned", "implemented", "verified", "blocked")


class EntryNotFoundError(ValueError):
    """Raised when an entry ID cannot be found in the history log."""


class HistoryEntry(NamedTuple):
    heading: str
    entry_id: str
    lines: tuple[str, ...]
    text: str


def parse_history(content: str) -> list[HistoryEntry]:
    entries: list[HistoryEntry] = []
    current_lines: list[str] = []

    for line in content.splitlines():
        if line.startswith("## "):
            _append_parsed_entry(entries, current_lines)
            current_lines = [line]
        elif current_lines:
            current_lines.append(line)

    _append_parsed_entry(entries, current_lines)
    return entries


def search_entries(
    *,
    history_path: Path,
    terms: Sequence[str],
    limit: int,
) -> list[HistoryEntry]:
    normalized_terms = [term.lower() for term in terms if term.strip()]
    if not normalized_terms:
        return []

    entries = _read_entries(history_path)
    scored: list[tuple[int, int, HistoryEntry]] = []
    for recent_index, entry in enumerate(reversed(entries)):
        text = entry.text.lower()
        score = sum(text.count(term) for term in normalized_terms)
        if score > 0:
            scored.append((score, recent_index, entry))

    scored.sort(key=lambda item: (item[1], -item[0]))
    return [entry for _, _, entry in scored[:limit]]


def append_entry(
    *,
    history_path: Path,
    title: str,
    goal: str,
    problem: str,
    similar_history: str,
    plan_fix: str,
    lessons: str,
    status: str,
    entry_id: str | None = None,
) -> HistoryEntry:
    _validate_status(status)
    resolved_id = entry_id or _generate_entry_id(title)
    entry = _entry_from_fields(
        title=title,
        entry_id=resolved_id,
        goal=goal,
        problem=problem,
        similar_history=similar_history,
        plan_fix=plan_fix,
        lessons=lessons,
        status=status,
    )

    entries = _read_entries(history_path)
    entries.append(entry)
    _write_entries(history_path, entries[-MAX_ENTRIES:])
    return entry


def update_entry_by_id(
    *,
    history_path: Path,
    entry_id: str,
    goal: str | None = None,
    problem: str | None = None,
    similar_history: str | None = None,
    plan_fix: str | None = None,
    lessons: str | None = None,
    status: str | None = None,
) -> HistoryEntry:
    if status is not None:
        _validate_status(status)

    entries = _read_entries(history_path)
    for index, entry in enumerate(entries):
        if entry.entry_id != entry_id:
            continue

        lines = list(entry.lines)
        field_updates = (
            ("Goal", goal),
            ("Problem", problem),
            ("Similar history", similar_history),
            ("Plan/fix", plan_fix),
            ("Lessons", lessons),
            ("Status", status),
        )
        for label, value in field_updates:
            if value is not None:
                lines = _set_field(lines, label, value)

        updated_entry = _entry_from_lines(lines)
        entries[index] = updated_entry
        _write_entries(history_path, entries[-MAX_ENTRIES:])
        return updated_entry

    raise EntryNotFoundError(f"No detailed-plan history entry found for {entry_id}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage logs/detailed-plan-history.md.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search")
    search_parser.add_argument("terms", nargs="+")
    search_parser.add_argument("--limit", type=int, default=5)
    search_parser.add_argument("--path", type=Path, default=HISTORY_PATH)

    append_parser = subparsers.add_parser("append")
    _add_entry_fields(append_parser)
    append_parser.add_argument("--id", dest="entry_id")
    append_parser.add_argument("--path", type=Path, default=HISTORY_PATH)

    update_parser = subparsers.add_parser("update-by-id")
    update_parser.add_argument("--id", dest="entry_id", required=True)
    _add_optional_entry_fields(update_parser)
    update_parser.add_argument("--path", type=Path, default=HISTORY_PATH)

    args = parser.parse_args()
    if args.command == "search":
        _print_search_results(args.path, args.terms, args.limit)
    elif args.command == "append":
        entry = append_entry(
            history_path=args.path,
            title=args.title,
            goal=args.goal,
            problem=args.problem,
            similar_history=args.similar_history,
            plan_fix=args.plan_fix,
            lessons=args.lessons,
            status=args.status,
            entry_id=args.entry_id,
        )
        _write_stdout(f"{entry.entry_id}\n")
    elif args.command == "update-by-id":
        entry = update_entry_by_id(
            history_path=args.path,
            entry_id=args.entry_id,
            goal=args.goal,
            problem=args.problem,
            similar_history=args.similar_history,
            plan_fix=args.plan_fix,
            lessons=args.lessons,
            status=args.status,
        )
        _write_stdout(f"{entry.entry_id}\n")


def _add_entry_fields(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--title", required=True)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--problem", required=True)
    parser.add_argument("--similar-history", required=True)
    parser.add_argument("--plan-fix", required=True)
    parser.add_argument("--lessons", required=True)
    parser.add_argument("--status", choices=VALID_STATUSES, required=True)


def _add_optional_entry_fields(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--goal")
    parser.add_argument("--problem")
    parser.add_argument("--similar-history")
    parser.add_argument("--plan-fix")
    parser.add_argument("--lessons")
    parser.add_argument("--status", choices=VALID_STATUSES)


def _print_search_results(history_path: Path, terms: Sequence[str], limit: int) -> None:
    entries = search_entries(history_path=history_path, terms=terms, limit=limit)
    if not entries:
        _write_stdout("No matching detailed-plan history entries.\n")
        return

    _write_stdout("\n\n".join(entry.text for entry in entries) + "\n")


def _append_parsed_entry(
    entries: list[HistoryEntry],
    current_lines: Sequence[str],
) -> None:
    if current_lines:
        entries.append(_entry_from_lines(current_lines))


def _entry_from_lines(lines: Sequence[str]) -> HistoryEntry:
    line_tuple = tuple(lines)
    heading = line_tuple[0].removeprefix("## ").strip()
    entry_id = _extract_field(line_tuple, "ID")
    text = "\n".join(line_tuple).strip()
    return HistoryEntry(
        heading=heading,
        entry_id=entry_id,
        lines=line_tuple,
        text=text,
    )


def _entry_from_fields(
    *,
    title: str,
    entry_id: str,
    goal: str,
    problem: str,
    similar_history: str,
    plan_fix: str,
    lessons: str,
    status: str,
) -> HistoryEntry:
    heading_time = utc_now().strftime("%Y-%m-%d %H:%M UTC")
    lines = (
        f"## {heading_time} | {_compact(title)}",
        f"- ID: {_compact(entry_id)}",
        f"- Goal: {_compact(goal)}",
        f"- Problem: {_compact(problem)}",
        f"- Similar history: {_compact(similar_history)}",
        f"- Plan/fix: {_compact(plan_fix)}",
        f"- Lessons: {_compact(lessons)}",
        f"- Status: {_compact(status)}",
    )
    return _entry_from_lines(lines)


def _extract_field(lines: Sequence[str], label: str) -> str:
    prefix = f"- {label}:"
    for line in lines:
        if line.startswith(prefix):
            return line.removeprefix(prefix).strip()
    return ""


def _set_field(lines: list[str], label: str, value: str) -> list[str]:
    prefix = f"- {label}:"
    replacement = f"{prefix} {_compact(value)}"
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = replacement
            return lines

    insert_at = len(lines)
    status_index = _find_status_index(lines)
    if label != "Status" and status_index is not None:
        insert_at = status_index
    lines.insert(insert_at, replacement)
    return lines


def _find_status_index(lines: Sequence[str]) -> int | None:
    for index, line in enumerate(lines):
        if line.startswith("- Status:"):
            return index
    return None


def _read_entries(history_path: Path) -> list[HistoryEntry]:
    if not history_path.exists():
        return []
    return parse_history(history_path.read_text(encoding="utf-8"))


def _write_entries(history_path: Path, entries: Sequence[HistoryEntry]) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n\n".join(entry.text for entry in entries)
    content = f"{HISTORY_TITLE}\n"
    if body:
        content = f"{content}\n{body}\n"
    history_path.write_text(content, encoding="utf-8")


def _generate_entry_id(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if not slug:
        slug = "entry"
    return f"{utc_now().strftime('%Y%m%dT%H%M%SZ')}-{slug[:48]}"


def _validate_status(status: str) -> None:
    if status not in VALID_STATUSES:
        valid_statuses = ", ".join(VALID_STATUSES)
        raise ValueError(f"Status must be one of: {valid_statuses}")


def _compact(value: str) -> str:
    compacted = " ".join(value.strip().split())
    return compacted or "none"


def _write_stdout(message: str) -> None:
    sys.stdout.write(message)


if __name__ == "__main__":
    main()

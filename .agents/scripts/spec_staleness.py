"""Can one spec's own citations still be trusted, or has the code they
describe moved on since the spec's own anchor?

Promoted from `verify/spec_staleness.py` (gitignored, ephemeral) into a real,
committed gate: `.agents/workflows/detailed-plan.md` §3 "Scope Wave 1 on
measured staleness" invokes this directly, before dispatching any evidence
scout, so a spec whose citations are already confirmed unchanged does not pay
for a fresh sweep it does not need. See
`docs/decision-notes/2026-08-04-agent-workflow-cost-control-plan.md` §10 P2 —
this is the "yield signal" lever sizing there names as replacing role
enumeration: across this repo's 35 engineering-ready specs, the number of
changed cited files ranged from 0 to 10, and Wave 1 previously cost the same
for both ends of that range.

The anchor is whichever key the input file carries: a `Derived-from-commit:`
sha pins the comparison to one commit (`<sha>..HEAD`), and a `**Updated:**`
date falls back to a date window (`--since=<date>`). A file carrying neither
cannot be checked at all.

Exit codes, read by the caller before its own text (`main`'s docstring states
the same contract `detailed-plan.md` was told to read):

- 0: every cited file exists and none changed since the anchor. Wave 1 may be
  skipped.
- 1: at least one cited file is missing, changed, or otherwise not verifiable
  (no anchor at all, or zero citations to check) -- run Wave 1.
- 2: the anchor names a commit this repository does not have. An error, not a
  verdict: nothing was measured, so neither 0 nor 1 would be true. Only a
  commit-anchored input can reach this, so a date-anchored spec still reads
  purely as 0/1.
"""

from __future__ import annotations

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
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


from agentic_workflows.exceptions import ContractViolation
import logging

logger = logging.getLogger(__name__)
from agentic_workflows.process_runner import run_safe_process

# Backtick-quoted repo-relative paths, e.g. `src/foo/bar.py` or
# `tests/unit/test_bar.py:42` (the `:line` suffix is stripped, not part of a
# path git can compare). Scoped to this repo's own top-level source
# directories so a backtick-quoted shell command or config key is never
# mistaken for a citation.
_CITATION = re.compile(
    r"`((?:src|tests|scripts|src-ui|\.agents|\.claude)/[\w./-]+\.\w+)(?::\d+)?`"
)

# Both anchor keys tolerate a leading `- `: measured across this repo's 84
# specs, 78 write `**Updated:**` at line start and 1 writes it as a list item.
# The prefix is optional on both so neither key's reach depends on whether its
# author happened to bullet the field.
_UPDATED_DATE = re.compile(
    r"^(?:- )?\*\*Updated:\*\*\s*(\d{4}-\d{2}-\d{2})", re.MULTILINE
)
_DERIVED_FROM_COMMIT = re.compile(
    r"^(?:- )?Derived-from-commit:\s*([0-9a-fA-F]{7,40})\b", re.MULTILINE
)


class AnchorKind(StrEnum):
    """Which key an input carried, and therefore how `git` is asked."""

    COMMIT = "commit"
    DATE = "date"


class CitedFileStatus(StrEnum):
    """One cited file's verdict against the anchor.

    `UNCHANGED` is the absence of an observed change, not proof of one: with
    no anchor nothing can be observed, which is why `StalenessResult.is_clean`
    gates on the anchor separately rather than reading these alone.
    """

    UNCHANGED = "unchanged"
    MODIFIED = "modified"
    DELETED = "deleted"


@dataclass(frozen=True)
class StalenessAnchor:
    """The point an input's citations are measured against.

    One model rather than two nullable fields on the result, so "a kind
    without its value" is unrepresentable instead of merely unlikely.
    """

    kind: AnchorKind
    value: str


class UnknownAnchorCommitError(ContractViolation):
    """The anchor names a commit this repository does not have.

    A deterministic violation of the stamp's own contract -- the identical
    input fails identically on a re-run -- so it is reported as an error
    rather than folded into a staleness verdict it cannot support.
    """

    def __init__(self, commit: str) -> None:
        self.commit = commit
        super().__init__(f"Anchor commit '{commit}' is not in this repository")


def extract_cited_files(text: str) -> set[str]:
    """Every distinct repo-relative path a spec's body cites in backticks."""
    return set(_CITATION.findall(text))


def extract_anchor(text: str) -> StalenessAnchor | None:
    """The input's own anchor, or None when it carries neither key.

    A commit sha wins over a date when both are present: it names an exact
    point in history, while a date only bounds one.
    """
    commit = _DERIVED_FROM_COMMIT.search(text)
    if commit:
        return StalenessAnchor(kind=AnchorKind.COMMIT, value=commit.group(1))
    date = _UPDATED_DATE.search(text)
    if date:
        return StalenessAnchor(kind=AnchorKind.DATE, value=date.group(1))
    return None


def _revision_span(repo: Path, anchor: StalenessAnchor) -> str:
    """The `git log` argument selecting every commit since `anchor`.

    Raises:
        UnknownAnchorCommitError: the anchor names a commit `repo` does not
            have, so no span over it can be built. Checked here, before any
            path filtering, so an input citing nothing that exists on disk
            still reports the bad anchor rather than a silent verdict.
    """
    if anchor.kind is AnchorKind.DATE:
        return f"--since={anchor.value}"
    resolved = run_safe_process(
        [
            "git",
            "-C",
            repo.as_posix(),
            "rev-parse",
            "--verify",
            "--quiet",
            f"{anchor.value}^{{commit}}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if resolved.returncode != 0:
        raise UnknownAnchorCommitError(anchor.value)
    return f"{anchor.value}..HEAD"


def _changed_paths(repo: Path, paths: set[str], anchor: StalenessAnchor) -> set[str]:
    """Every one of `paths` that `git log` shows touched since `anchor`,
    scoped to files git actually tracks.

    Deliberately not the caller's job to filter to existing files first:
    `git log` on a path git never tracked (a typo, or one already deleted
    before the anchor) returns nothing, which is indistinguishable from
    "unchanged" -- callers must combine this with an existence check to catch
    that case (`check_spec_staleness` does, via `CitedFileStatus.DELETED`).
    """
    span = _revision_span(repo, anchor)
    if not paths:
        return set()
    result = run_safe_process(
        [
            "git",
            "-C",
            repo.as_posix(),
            "log",
            span,
            "--name-only",
            "--pretty=format:",
            "--",
            *sorted(paths),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


@dataclass(frozen=True)
class StalenessResult:
    """One spec's staleness verdict against the current repository state."""

    anchor: StalenessAnchor | None
    file_statuses: dict[str, CitedFileStatus]

    @property
    def cited_files(self) -> frozenset[str]:
        """Every path the input cites -- one key per file, status or not."""
        return frozenset(self.file_statuses)

    @property
    def missing_files(self) -> frozenset[str]:
        """The cited files no longer on disk."""
        return self._paths_with(CitedFileStatus.DELETED)

    @property
    def changed_files(self) -> frozenset[str]:
        """The cited files git shows touched since the anchor."""
        return self._paths_with(CitedFileStatus.MODIFIED)

    def _paths_with(self, status: CitedFileStatus) -> frozenset[str]:
        return frozenset(
            path for path, verdict in self.file_statuses.items() if verdict is status
        )

    @property
    def is_clean(self) -> bool:
        """True only when every citation is checkable and none moved.

        False for an input with no anchor or no citations at all -- neither is
        verifiable, and treating "cannot check" as "assume clean" would
        silently skip Wave 1 on exactly the specs least entitled to that
        discount.
        """
        return bool(self.anchor and self.file_statuses) and all(
            verdict is CitedFileStatus.UNCHANGED
            for verdict in self.file_statuses.values()
        )


def check_spec_staleness(repo: Path, spec_path: Path) -> StalenessResult:
    """One input's staleness verdict: which of its cited files are gone or
    have changed since its own anchor.

    Raises:
        UnknownAnchorCommitError: the anchor names a commit `repo` does not
            have. No verdict is returned, because none was measured.
    """
    text = spec_path.read_text(encoding="utf-8", errors="replace")
    anchor = extract_anchor(text)
    cited = extract_cited_files(text)
    existing = {path for path in cited if (repo / path).exists()}
    changed = _changed_paths(repo, existing, anchor) if anchor else set()
    file_statuses: dict[str, CitedFileStatus] = {}
    for path in sorted(cited):
        if path not in existing:
            file_statuses[path] = CitedFileStatus.DELETED
        elif path in changed:
            file_statuses[path] = CitedFileStatus.MODIFIED
        else:
            file_statuses[path] = CitedFileStatus.UNCHANGED
    return StalenessResult(anchor=anchor, file_statuses=file_statuses)


def main() -> int:
    """Check one input's staleness against the current repository state.

    Returns 0 when Wave 1 may be skipped (every citation verified unchanged),
    1 when it cannot be (a citation moved, or the input is unverifiable), and
    2 when the anchor names a commit this repository does not have -- an
    error rather than a verdict, reachable only from a commit-anchored input.
    Read the printed reason, not just the exit code: it says which citations
    moved, which are missing, or why the input was unverifiable.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Check whether an input's cited files have changed since its own "
            "Derived-from-commit: sha or Updated: date, to scope "
            "detailed-plan's Wave 1 dispatch."
        )
    )
    parser.add_argument("spec_path", type=Path, help="Path to the spec Markdown file.")
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(),
        help="Repository root to check citations and git history against.",
    )
    args = parser.parse_args()

    spec_path: Path = args.spec_path
    if not spec_path.is_file():
        logger.error("No such spec file: %s", spec_path)
        return 1

    try:
        result = check_spec_staleness(args.repo.resolve(), spec_path)
    except UnknownAnchorCommitError as error:
        logger.error("%s: %s; nothing could be measured.", spec_path, error)
        return 2

    if result.anchor is None:
        logger.info(
            "%s: no 'Derived-from-commit:' sha and no 'Updated:' date; "
            "cannot verify freshness.",
            spec_path,
        )
        return 1
    if not result.cited_files:
        logger.info("%s: cites no file; cannot be staleness-checked at all.", spec_path)
        return 1

    logger.info(
        "%s: %d cited file(s), %d missing, %d changed since %s %s.",
        spec_path,
        len(result.cited_files),
        len(result.missing_files),
        len(result.changed_files),
        result.anchor.kind.value,
        result.anchor.value,
    )
    if result.missing_files:
        logger.info("  Missing: %s", ", ".join(sorted(result.missing_files)))
    if result.changed_files:
        logger.info("  Changed: %s", ", ".join(sorted(result.changed_files)))

    return 0 if result.is_clean else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""File-partitioned batching for the review-fix loop's parallel fix phase.

The loop historically applied findings sequentially, one at a time, in the
working tree — 13 sequential batches measured at $591 and a ~15h tail. The
accepted design (DD-002, 2026-09-17) reverses that rule: findings are split
into at most N file-disjoint batches so parallel fixers never edit the same
file, which is the load-bearing invariant for rolling merges (REQ-005).

This module owns only that grouping decision and holds no I/O, so the rule
is testable without a filesystem. N arrives as a plain argument — the
calling loop owns the config read; nothing here ever reads
`.agents/config.toml`.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

FindingSeverity = Literal["critical", "important", "minor"]

# Critical -> Important -> Minor, the loop's canonical severity order;
# it decides batch order, merge order, and deferral order alike.
_SEVERITY_RANK: dict[FindingSeverity, int] = {
    "critical": 0,
    "important": 1,
    "minor": 2,
}


@dataclass(frozen=True)
class ReviewFinding:
    """One confirmed loop finding, reduced to what batching needs to know.

    The loop synthesizes richer findings (dimension, evidence, fix sketch);
    it maps them onto this shape before batching and resolves batches back
    through `finding_id`. A finding that touches no file cannot be
    partitioned, so an empty file set is rejected at the boundary.
    """

    finding_id: str
    severity: FindingSeverity
    files: frozenset[Path]

    def __post_init__(self) -> None:
        if not self.finding_id:
            raise ValueError("finding_id must be a non-empty string")
        if self.severity not in _SEVERITY_RANK:
            raise ValueError(
                f"severity must be one of {sorted(_SEVERITY_RANK)}, "
                f"got {self.severity!r}"
            )
        if len(self.files) < 1:
            raise ValueError("files must contain at least one path")


@dataclass(frozen=True)
class FixBatch:
    """One fixer's work order: findings whose files no other batch shares.

    `files` holds the canonical keys the partitioner computed for every
    cited spelling — the disjoint currency cross-batch safety is claimed
    against — while each finding keeps its caller-facing path spellings.

    `merged` is set when forcing the batch count under N absorbed other
    partitions into this one, so the loop report can show which slots were
    collapsed rather than independently scheduled.
    """

    batch_id: int
    findings: list[ReviewFinding] = field(default_factory=list)
    files: frozenset[Path] = field(default_factory=frozenset)
    merged: bool = False

    def __post_init__(self) -> None:
        if not self.findings:
            raise ValueError("findings must contain at least one finding")
        if not self.files:
            raise ValueError("files must contain at least one path")


@dataclass(frozen=True)
class PartitionResult:
    """The batches to dispatch, plus findings pushed to the next iteration."""

    batches: list[FixBatch]
    deferred: list[ReviewFinding]


def _relative_to_repo_root(folded: str, repo_root: Path, original: Path) -> str:
    """Fold a repo-internal citation to root-relative, or fail fast.

    `folded` is the separator-unified, casefolded citation; `original` is
    kept only to name the input in errors. Absolute citations under the
    repo root return root-relative; a citation that cannot live under the
    root raises `ValueError` — the module's contract is repo-internal
    paths, and silently keying an outside path differently from every
    repo-internal spelling of it is the bug this refuses.
    """
    root = repo_root.as_posix().replace("\\", "/").rstrip("/").casefold()
    if not folded.startswith("/"):
        relative = folded
    elif folded == root:
        relative = "."
    elif folded.startswith(f"{root}/"):
        relative = folded[len(root) + 1 :]
    else:
        raise ValueError(
            f"path {original.as_posix()!r} is outside repo_root "
            f"{repo_root.as_posix()!r}; the partitioner only accepts "
            "repo-internal paths"
        )
    normalized = posixpath.normpath(relative)
    if normalized == ".." or normalized.startswith("../"):
        raise ValueError(
            f"path {original.as_posix()!r} escapes repo_root "
            f"{repo_root.as_posix()!r} via '..'; the partitioner only "
            "accepts repo-internal paths"
        )
    return normalized


def _canonical_key(path: Path, repo_root: Path | None = None) -> Path:
    """Identity contract for file comparison; never a replacement value.

    Finding paths come from LLM-authored review output, so one physical
    file can arrive as `src/a.py`, `src\\utils\\a.py` (Windows-style
    separator leakage), `Src/A.py`, `/src/a.py`, or `src/x/../a.py`. Every
    variant must produce this same key or parallel fixers can be
    dispatched into one file (DD-002). The key therefore unifies
    separators, collapses `.`/`..` segments, folds case, and treats
    relative and absolute spellings as one. Pure lexical normalization
    via `posixpath` (not `os.path`) — no filesystem access.

    Case folding (`str.casefold`) encodes the case-insensitive-volume
    assumption: development runs on darwin/APFS where `Src/A.py` and
    `src/a.py` are one file. On a case-sensitive filesystem this can only
    over-merge two genuinely distinct paths into one batch — the safe
    direction for disjointness.

    With `repo_root`, a host-absolute citation under the root
    (`/Users/me/repo/src/a.py`) relativizes before normalization so it
    matches its relative spelling; a citation outside the root, or one
    escaping it via `..`, raises `ValueError` naming the input. Without
    `repo_root` an absolute citation cannot be matched to its relative
    spelling, so it would silently land in a second batch — two fixers
    in one file, the unsafe direction — and therefore also raises
    `ValueError` naming the input; the degraded mode accepts only
    relative citations.
    """
    folded = path.as_posix().replace("\\", "/").casefold()
    if repo_root is None:
        if path.is_absolute():
            raise ValueError(
                f"path {path.as_posix()!r} is absolute but repo_root was "
                "not provided; an absolute citation cannot be matched to "
                "its relative spelling there, so batching would silently "
                "split one file across parallel fixers"
            )
    else:
        folded = _relative_to_repo_root(folded, repo_root, path)
    return Path(posixpath.normpath(f"/{folded.lstrip('/')}"))


def _finding_key(finding: ReviewFinding) -> tuple[int, str]:
    return (_SEVERITY_RANK[finding.severity], finding.finding_id)


@dataclass
class _Partition:
    """Findings connected by shared files; `merged` survives into the batch."""

    findings: list[ReviewFinding]
    merged: bool = False

    @property
    def rank(self) -> int:
        # Findings stay severity-sorted, so the head is the partition's
        # highest severity — what the partition is worth as a batch.
        return _SEVERITY_RANK[self.findings[0].severity]


def _partition_key(partition: _Partition) -> tuple[int, int, str]:
    # Most severe first; a partition holding more findings would serialize
    # more work behind a merge, so it wins the tie; finding_id makes the
    # output deterministic for equal shapes.
    head = partition.findings[0]
    return (partition.rank, -len(partition.findings), head.finding_id)


class _FileUnion:
    """Union-find over file paths: shared file implies shared batch."""

    def __init__(self) -> None:
        self._parent: dict[Path, Path] = {}

    def add(self, path: Path) -> None:
        self._parent.setdefault(path, path)

    def find(self, path: Path) -> Path:
        root = path
        while self._parent[root] != root:
            root = self._parent[root]
        return root

    def union(self, left: Path, right: Path) -> None:
        self._parent[self.find(right)] = self.find(left)


def partition_findings(
    findings: list[ReviewFinding],
    n: int,
    *,
    edited_files: frozenset[Path] = frozenset(),
    repo_root: Path | None = None,
) -> PartitionResult:
    """Group findings into at most N file-disjoint fixer batches.

    Findings are union-found over their file sets, so any two findings
    touching the same file land in the same batch no matter how many
    batches remain. Paths are compared through `_canonical_key`, so
    differently spelled citations of one file (`..`-dotted,
    backslash, or case variants from LLM-authored output) still share a
    batch; with `repo_root`, host-absolute citations under the root match
    their relative spelling and citations outside the root fail fast;
    without it an absolute citation fails fast rather than silently
    under-merging.
    `edited_files` membership uses the same canonical form, and each
    batch's `files` exposes those canonical keys — the disjoint currency
    across batches. More than N disjoint partitions merges tail-first by
    severity — the two lowest-value partitions fold together repeatedly
    until the count is <= N, so Critical slots survive longest. A single
    hot file therefore yields exactly one batch regardless of N (EC-009).

    Findings citing a file in `edited_files` — the union of files prior
    batches already edited — cannot be scheduled this iteration without
    colliding with landed work, so they defer to the next iteration's
    finding list (EC-006), returned severity-ordered for the loop report.
    """
    if n < 1:
        raise ValueError(f"n must be >= 1 to cap parallel fixers, got {n}")

    def canonical(path: Path) -> Path:
        return _canonical_key(path, repo_root)

    edited_keys = frozenset(canonical(path) for path in edited_files)

    def cites_edited(finding: ReviewFinding) -> bool:
        return any(canonical(path) in edited_keys for path in finding.files)

    deferred = sorted(
        (finding for finding in findings if cites_edited(finding)),
        key=_finding_key,
    )
    schedulable = [finding for finding in findings if not cites_edited(finding)]

    union = _FileUnion()
    for finding in schedulable:
        for path in sorted(canonical(p) for p in finding.files):
            union.add(path)
    for finding in schedulable:
        ordered = sorted(canonical(p) for p in finding.files)
        for path in ordered[1:]:
            union.union(ordered[0], path)

    grouped: dict[Path, list[ReviewFinding]] = {}
    for finding in schedulable:
        root = union.find(min(canonical(p) for p in finding.files))
        grouped.setdefault(root, []).append(finding)

    partitions = [
        _Partition(sorted(group, key=_finding_key)) for group in grouped.values()
    ]
    partitions.sort(key=_partition_key)

    while len(partitions) > n:
        tail = partitions.pop()
        absorbed = partitions.pop()
        combined = _Partition(
            sorted(absorbed.findings + tail.findings, key=_finding_key),
            merged=True,
        )
        partitions.append(combined)
        partitions.sort(key=_partition_key)

    batches = [
        FixBatch(
            batch_id=index + 1,
            findings=partition.findings,
            files=frozenset(
                canonical(path)
                for finding in partition.findings
                for path in finding.files
            ),
            merged=partition.merged,
        )
        for index, partition in enumerate(partitions)
    ]
    return PartitionResult(batches=batches, deferred=deferred)

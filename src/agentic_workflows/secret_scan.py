"""Value-shape-based secret detection, stdlib-only.

This module is deliberately conservative about what a secret looks like: it
matches well-known credential shapes (cloud keys, provider tokens, private-key
banners) and keyword-assigned high-entropy values. It is a heuristic pre-push
gate, not a security boundary and not an exhaustive scanner -- consumers that
want broader plugin-based detection can swap this module for a
`detect-secrets`-backed implementation with the same public API. Every rule
here errs toward false positives on ADDED diff lines only, where the cost of
a false positive is one human glance.

Redaction is exact-value replacement wherever the matched value is captured;
the one exception is a private-key banner, whose regex matches only the banner
line and never the base64 key body that follows -- no set of exact-value
replacements can remove that key material, so the whole text is withheld
instead of surgically redacted.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass

# What a redacted secret is replaced with. Fixed and generic on purpose: it must
# never itself be mistaken for a real value, and it must not vary by secret type
# (varying it would leak a little of what kind of credential was there).
REDACTION_PLACEHOLDER = "[REDACTED]"

# Detector types whose match is a fixed marker string, not the actual sensitive
# payload (the private-key banner case described in the module docstring).
_MARKER_ONLY_SECRET_TYPES = frozenset({"Private Key"})

# Shannon-entropy floor for keyword-assigned values, in bits per character.
# Ordinary words sit near 2.5-3.0; random tokens sit near 4+. The floor keeps
# `password = "correct-horse-battery"` style prose from matching while letting
# generated credentials through.
_MIN_ENTROPY_BITS_PER_CHAR = 3.2
_MIN_KEYWORD_VALUE_LENGTH = 16


def _shannon_entropy(text: str) -> float:
    if not text:
        return 0.0
    counts: dict[str, int] = {}
    for char in text:
        counts[char] = counts.get(char, 0) + 1
    total = len(text)
    return -sum(
        (count / total) * math.log2(count / total) for count in counts.values()
    )


def _keyword_value(value: str) -> str | None:
    """The assigned value, when it is long and high-entropy enough."""
    if len(value) < _MIN_KEYWORD_VALUE_LENGTH:
        return None
    if _shannon_entropy(value) < _MIN_ENTROPY_BITS_PER_CHAR:
        return None
    return value


# (secret type, pattern, value group index or None for marker-only matches).
# Group 0 is the full match; a positive group names the captured secret value.
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str], int | None], ...] = (
    (
        "Private Key",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        None,
    ),
    (
        "AWS Access Key",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        0,
    ),
    (
        "GitHub Token",
        re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,255}\b"),
        0,
    ),
    (
        "GitHub Fine-Grained Token",
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{60,255}\b"),
        0,
    ),
    (
        "Slack Token",
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,250}\b"),
        0,
    ),
    (
        "Google API Key",
        re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
        0,
    ),
    (
        "OpenAI API Key",
        re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{20,250}\b"),
        0,
    ),
    (
        "Anthropic API Key",
        re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,250}\b"),
        0,
    ),
    (
        "Assigned Secret",
        re.compile(
            r"(?:api[_-]?key|apikey|secret|token|password|passwd|pwd|credential)"
            r"\s*[:=]\s*['\"]?([A-Za-z0-9_\-/.+=]{16,250})['\"]?",
            re.IGNORECASE,
        ),
        1,
    ),
)


@dataclass(frozen=True)
class SecretMatch:
    """A detected credential-shaped value's location and type -- never its value.

    Keeping the matched value itself out of this type is intentional: any
    denial message built from a `SecretMatch` can never leak the secret it
    describes.
    """

    line_number: int
    secret_type: str


@dataclass(frozen=True)
class SecretScanResult:
    """What one scan of a piece of text found, in exactly the shape a caller needs
    to redact that text -- and any other text derived from it -- safely and
    consistently, without a second scan.

    `needs_full_redaction` is true when a marker-only detector matched (see
    `_MARKER_ONLY_SECRET_TYPES`): in that case `secret_values` must not be trusted
    to fully describe what is sensitive, and a caller must withhold the whole text
    instead of attempting a surgical replacement.
    """

    needs_full_redaction: bool
    secret_values: frozenset[str]


def _scan_lines(text: str) -> list[tuple[int, str, str | None]]:
    """(line number, secret type, matched value or None) for every match."""
    found: list[tuple[int, str, str | None]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for secret_type, pattern, value_group in _SECRET_PATTERNS:
            for match in pattern.finditer(line):
                if value_group is None:
                    found.append((line_number, secret_type, None))
                    continue
                value = match.group(value_group)
                if value_group == 0:
                    found.append((line_number, secret_type, value))
                    continue
                # Keyword-assigned rule: the captured value must clear the
                # entropy gate, or the keyword alone is not a finding.
                retained = _keyword_value(value)
                if retained is not None:
                    found.append((line_number, secret_type, retained))
    return found


def scan_for_redaction(text: str) -> SecretScanResult:
    """Scan `text` once for the purpose of redacting it, and anything derived
    from it, safely.

    A single scan is deliberate: a caller that needs to redact both `text` and a
    second string *derived* from it (e.g. a checker finding's `detail` message,
    which can embed a literal excerpt of `text`) must apply the exact same
    decision to both, not scan each independently.
    """
    if not text:
        return SecretScanResult(needs_full_redaction=False, secret_values=frozenset())

    found = _scan_lines(text)
    return SecretScanResult(
        needs_full_redaction=any(
            secret_type in _MARKER_ONLY_SECRET_TYPES for _, secret_type, _ in found
        ),
        secret_values=frozenset(
            value for _, _, value in found if value is not None
        ),
    )


def find_secret_values(text: str) -> frozenset[str]:
    """The unique matched values found anywhere in `text`.

    A thin, independently useful accessor over `scan_for_redaction` for a caller
    that only needs the exact-value set (e.g. a test asserting what was found) and
    does not need to handle the marker-only whole-redaction case itself.
    """
    return scan_for_redaction(text).secret_values


def redact_known_secret_values(text: str, secret_values: Iterable[str]) -> str:
    """Replace every occurrence of any value in `secret_values` with a fixed
    placeholder, longest value first.

    Ordering matters: if one matched value is a substring of another (a
    keyword/prefix rule catching a token's prefix while a separate high-entropy
    rule separately catches the whole token, for one confirmed real case),
    redacting the shorter one first would destroy the longer one's exact text
    before its own replacement runs, leaving most of the real secret exposed.
    Redacting the longest value first consumes any shorter value it contains as a
    side effect, making the shorter value's own now-impossible match a harmless
    no-op instead.
    """
    redacted = text
    for value in sorted(
        {value for value in secret_values if value}, key=len, reverse=True
    ):
        redacted = redacted.replace(value, REDACTION_PLACEHOLDER)
    return redacted


def redact_secrets(text: str) -> str:
    """Replace every credential-shaped value found in `text` with a fixed placeholder.

    Redaction is a literal, exact-value replacement for matches whose value is
    captured, not a whole-line or span-offset scheme. The one exception is a
    marker-only match (see `_MARKER_ONLY_SECRET_TYPES`), where `text` is
    withheld entirely instead, since no exact-value replacement could remove the
    actual secret in that case. `SecretMatch` itself still never carries any
    matched value; nothing about this function changes that guarantee, since it
    only ever returns redacted text.
    """
    if not text:
        return text

    result = scan_for_redaction(text)
    if result.needs_full_redaction:
        return REDACTION_PLACEHOLDER
    return redact_known_secret_values(text, result.secret_values)


def scan_text_for_secrets(text: str) -> list[SecretMatch]:
    """Return every credential-shaped value found in `text`.

    Line numbers are 1-indexed and relative to `text` as given.
    """
    if not text:
        return []
    return [
        SecretMatch(line_number=line_number, secret_type=secret_type)
        for line_number, secret_type, _ in _scan_lines(text)
    ]


def scan_diff_for_secrets(diff_text: str) -> list[SecretMatch]:
    """Return credential-shaped values found on added (`+`) lines of a unified diff.

    Only lines a change actually introduces matter for a pre-push secret
    gate -- unchanged context lines and removed lines aren't something this
    change is adding to the remote branch, so matches confined to them are
    excluded. Line numbers are 1-indexed and relative to `diff_text` as given
    (the same numbering `scan_text_for_secrets` would report for the whole
    diff), not renumbered relative to the new file.
    """
    if not diff_text:
        return []

    matches = scan_text_for_secrets(diff_text)

    added_line_numbers = {
        index
        for index, line in enumerate(diff_text.splitlines(), start=1)
        if line.startswith("+") and not line.startswith("+++")
    }
    return [match for match in matches if match.line_number in added_line_numbers]

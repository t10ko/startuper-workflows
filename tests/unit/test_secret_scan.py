"""The stdlib heuristic secret scanner (value-shape detection).

This file was ported from the detect-secrets-backed scanner's tests and
rewritten against the standalone scanner's documented behaviors: the public
API is identical (`REDACTION_PLACEHOLDER`, `SecretMatch(line_number,
secret_type)`, `SecretScanResult(needs_full_redaction, secret_values)`,
`scan_for_redaction`, `find_secret_values`, `redact_known_secret_values`,
`redact_secrets`, `scan_text_for_secrets`, `scan_diff_for_secrets`), but the
detection rules differ in two ways the tests below pin deliberately:

- a keyword-assigned value must clear a Shannon-entropy floor of 3.2
  bits/char and a minimum length of 16, or the keyword alone is not a
  finding (detect-secrets instead ran separate plugin detectors, including a
  base64/high-entropy one that flagged a token's `ghp` prefix as a second,
  overlapping match; the heuristic matches the whole token in one rule, so
  the overlapping-value case is exercised through `redact_known_secret_values`
  where the caller supplies both values);
- a private-key PEM banner is a marker-only match: no exact value is
  captured at all (detect-secrets captured the banner phrase itself), so
  `find_secret_values` returns nothing for it and redaction must withhold
  the whole text.
"""

from __future__ import annotations

import dataclasses

import pytest

from agentic_workflows.secret_scan import (
    REDACTION_PLACEHOLDER,
    SecretMatch,
    find_secret_values,
    redact_known_secret_values,
    redact_secrets,
    scan_diff_for_secrets,
    scan_for_redaction,
    scan_text_for_secrets,
)

# AWS's own official example access key ID. Intentionally public/fake --
# documented at https://docs.aws.amazon.com/general/latest/gr/aws-access-keys-best-practices.html
# -- safe to use in tests without embedding a real secret.
EXAMPLE_AWS_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"


def test_scan_text_for_secrets_detects_real_credential_shaped_value():
    text = f'aws_access_key_id = "{EXAMPLE_AWS_ACCESS_KEY}"'

    matches = scan_text_for_secrets(text)

    assert len(matches) == 1
    assert matches[0].line_number == 1
    assert "AWS" in matches[0].secret_type


def test_scan_text_for_secrets_ignores_bare_secret_name_mention():
    text = "This uses BITBUCKET_TOKEN for auth against the Bitbucket API."

    matches = scan_text_for_secrets(text)

    assert matches == []


def test_scan_text_for_secrets_returns_empty_list_for_empty_text():
    assert scan_text_for_secrets("") == []


def test_secret_match_never_exposes_the_matched_value():
    field_names = {field.name for field in dataclasses.fields(SecretMatch)}

    # Only a line number and a type label -- never the secret itself, so a
    # denial message built from a SecretMatch can never leak the value.
    assert field_names == {"line_number", "secret_type"}


def test_secret_match_is_frozen():
    match = SecretMatch(line_number=1, secret_type="AWS Access Key")  # noqa: S106

    with pytest.raises(dataclasses.FrozenInstanceError):
        match.line_number = 2  # type: ignore[misc]


# --- provider token shapes the heuristic matches -------------------------


def test_a_github_personal_access_token_shape_is_matched_as_one_whole_value():
    # Unlike detect-secrets' plugin set, which flagged the `ghp` prefix and the
    # whole token as two overlapping matches, the heuristic has one GitHub
    # rule and it captures the entire token. The full value (not a prefix) is
    # what lands in the redaction set, which is what makes an exact-value
    # replacement safe without any ordering argument at scan time.
    token = "ghp_1234567890abcdefghijklmnopqrstuvwxyz12"  # noqa: S105
    values = find_secret_values(f'private_token = "{token}"')

    assert values == frozenset({token})


@pytest.mark.parametrize(
    ("text", "expected_type"),
    [
        ('id = "AKIAIOSFODNN7EXAMPLE"', "AWS Access Key"),
        ('t = "ghp_1234567890abcdefghijklmnopqrstuvwxyz12"', "GitHub Token"),
        ('t = "github_pat_' + "A" * 60 + '"', "GitHub Fine-Grained Token"),
        ('t = "xoxb-123456789-abcdefghij"', "Slack Token"),
        ('t = "AIza' + "a" * 35 + '"', "Google API Key"),
        ('t = "sk-proj-abcdefghijklmnopqrst"', "OpenAI API Key"),
        # An `sk-ant-...` value also satisfies the looser OpenAI shape, so both
        # rules report it; the Anthropic finding must be among them.
        ('t = "sk-ant-abcdefghijklmnopqrst"', "Anthropic API Key"),
    ],
)
def test_each_documented_provider_token_shape_is_matched(text: str, expected_type: str):
    matches = scan_text_for_secrets(text)

    assert matches, f"no match at all for {text!r}"
    assert any(expected_type in match.secret_type for match in matches)


# --- keyword-assigned values: the entropy and length floors --------------


def test_a_keyword_assigned_value_must_clear_the_entropy_floor():
    # 16 chars long, but only ~2.75 bits/char: prose-shaped, not a generated
    # credential. The keyword alone is not a finding.
    assert find_secret_values('password = "passwordpassword"') == frozenset()


def test_a_keyword_assigned_value_must_clear_the_length_floor():
    # 15 chars of maximal entropy: one character short of the 16-char floor.
    assert find_secret_values('token = "Zk9mP2qR7vXw4yJ"') == frozenset()


def test_a_long_high_entropy_keyword_assigned_value_is_matched():
    # 16 chars, 4.0 bits/char: exactly what a generated credential looks like.
    assert find_secret_values('token = "Zk9mP2qR7vXw4yJ6"') == frozenset(
        {"Zk9mP2qR7vXw4yJ6"}
    )


def test_a_zero_entropy_value_of_sufficient_length_is_still_not_matched():
    assert find_secret_values('password = "aaaaaaaaaaaaaaaa"') == frozenset()


def test_a_value_below_the_floors_does_not_weaken_a_real_match_on_the_same_line():
    # The floors gate only the keyword-assigned rule: a structural shape on
    # the same line is matched regardless.
    text = f'aws_access_key_id = "{EXAMPLE_AWS_ACCESS_KEY}"\npassword = "aaa"'
    matches = scan_text_for_secrets(text)

    assert len(matches) == 1
    assert "AWS" in matches[0].secret_type


# --- diff scanning --------------------------------------------------------


def test_scan_diff_for_secrets_only_flags_added_lines():
    diff_text = (
        "--- a/config.py\n"
        "+++ b/config.py\n"
        "@@ -1,2 +1,3 @@\n"
        " unchanged_line = 1\n"
        f'-old_removed_key = "{EXAMPLE_AWS_ACCESS_KEY}"\n'
        f'+aws_access_key_id = "{EXAMPLE_AWS_ACCESS_KEY}"\n'
        "+print(1)\n"
    )

    matches = scan_diff_for_secrets(diff_text)

    assert len(matches) == 1
    assert matches[0].line_number == 6
    assert "AWS" in matches[0].secret_type


def test_scan_diff_for_secrets_ignores_secrets_confined_to_removed_or_context_lines():
    diff_text = (
        "--- a/config.py\n"
        "+++ b/config.py\n"
        "@@ -1,2 +1,2 @@\n"
        f' unchanged_context_key = "{EXAMPLE_AWS_ACCESS_KEY}"\n'
        f'-removed_key = "{EXAMPLE_AWS_ACCESS_KEY}"\n'
        "+harmless_added_line = 1\n"
    )

    assert scan_diff_for_secrets(diff_text) == []


def test_scan_diff_for_secrets_ignores_bare_secret_name_mention_on_added_line():
    diff_text = "--- a/README.md\n+++ b/README.md\n+Uses BITBUCKET_TOKEN for auth.\n"

    assert scan_diff_for_secrets(diff_text) == []


# --- redaction ------------------------------------------------------------


def test_redact_secrets_replaces_the_exact_matched_value():
    text = f'aws_access_key_id = "{EXAMPLE_AWS_ACCESS_KEY}"'

    redacted = redact_secrets(text)

    assert EXAMPLE_AWS_ACCESS_KEY not in redacted
    assert REDACTION_PLACEHOLDER in redacted
    assert redacted == f'aws_access_key_id = "{REDACTION_PLACEHOLDER}"'


def test_redact_secrets_leaves_clean_text_untouched():
    text = "Two ordinary sentences. Nothing secret about them."

    assert redact_secrets(text) == text


def test_redact_secrets_leaves_a_bare_secret_name_mention_untouched():
    text = "This uses BITBUCKET_TOKEN for auth against the Bitbucket API."

    assert redact_secrets(text) == text


def test_redact_secrets_returns_empty_string_for_empty_text():
    assert redact_secrets("") == ""


def test_redact_secrets_redacts_every_occurrence_of_a_repeated_secret():
    text = (
        f'first = "{EXAMPLE_AWS_ACCESS_KEY}"\n'
        f'again_same_value = "{EXAMPLE_AWS_ACCESS_KEY}"'
    )

    redacted = redact_secrets(text)

    assert EXAMPLE_AWS_ACCESS_KEY not in redacted
    assert redacted.count(REDACTION_PLACEHOLDER) == 2


def test_redact_secrets_redacts_two_distinct_secrets_in_the_same_text():
    """A single loop over every match, not just the first one found -- and each
    match's own value, not just the first match's, must be replaced. A second,
    structurally-valid AWS-access-key-shaped value (same regex shape as
    `EXAMPLE_AWS_ACCESS_KEY` above, not itself independently AWS-documented, but
    equally not a real credential) distinct from the first."""
    second_fake_key = "AKIAZZZZZZZZZZEXAMPL"
    text = f'first = "{EXAMPLE_AWS_ACCESS_KEY}"\nsecond = "{second_fake_key}"'

    redacted = redact_secrets(text)

    assert EXAMPLE_AWS_ACCESS_KEY not in redacted
    assert second_fake_key not in redacted
    assert redacted.count(REDACTION_PLACEHOLDER) == 2


# A syntactically well-formed but non-functional OpenSSH private key -- generated
# specifically for this test, never used to authenticate anything, safe to commit.
# The point is the PEM banner/footer shape, not that the key material is "real":
# the heuristic's private-key rule matches only the banner line, never the body.
FAKE_PRIVATE_KEY_BODY = (
    "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAABlwAAAAdzc2gtcn"
    "NhAAAAAwEAAQAAAYEA1c7g8h3j2k1l0p9o8i7u6y5t4r3e2w1q0a9s8d7f6g5h4j3k2l1p0"
    "o9i8u7y6t5r4e3w2q1r0t9y8u7i6o5p4a3s2d1f0g9h8j7k6l5p4o3i2u1y0t9r8e7w6q5"
)
FAKE_PRIVATE_KEY = (
    "-----BEGIN OPENSSH PRIVATE KEY-----\n"
    f"{FAKE_PRIVATE_KEY_BODY}\n"
    "-----END OPENSSH PRIVATE KEY-----"
)


def test_a_private_key_banner_captures_no_value_at_all():
    """The banner is a marker-only match: nothing value-shaped is captured, so
    `find_secret_values` cannot describe what is sensitive here -- which is
    exactly why `redact_secrets`/`scan_for_redaction` must treat this case
    specially instead of trusting a surgical value replacement. The base64
    key body in particular must never appear in the value set."""
    values = find_secret_values(FAKE_PRIVATE_KEY)

    assert FAKE_PRIVATE_KEY_BODY not in values
    assert "PRIVATE KEY" not in " ".join(values)


def test_redact_secrets_withholds_the_whole_text_for_a_private_key():
    """The bug this guards against: redacting only a matched banner text left
    the actual base64 key body completely exposed. A match that cannot cover
    the real secret must fall back to withholding everything, not a partial
    redaction that looks safe but isn't."""
    redacted = redact_secrets(FAKE_PRIVATE_KEY)

    assert FAKE_PRIVATE_KEY_BODY not in redacted
    assert redacted == REDACTION_PLACEHOLDER


def test_scan_for_redaction_reports_needs_full_redaction_for_a_private_key():
    result = scan_for_redaction(FAKE_PRIVATE_KEY)

    assert result.needs_full_redaction is True


def test_scan_for_redaction_does_not_need_full_redaction_for_an_ordinary_secret():
    result = scan_for_redaction(f'aws_access_key_id = "{EXAMPLE_AWS_ACCESS_KEY}"')

    assert result.needs_full_redaction is False
    assert result.secret_values == frozenset({EXAMPLE_AWS_ACCESS_KEY})


def test_scan_for_redaction_needs_no_redaction_for_clean_text():
    result = scan_for_redaction("Two ordinary sentences.")

    assert result.needs_full_redaction is False
    assert result.secret_values == frozenset()


def test_redact_known_secret_values_redacts_a_short_string_using_values_found_elsewhere():
    """The point of splitting `find_secret_values` out from `redact_secrets`: a
    short, isolated derived string (e.g. one finding's `detail` message) may
    no longer contain the line context a scan needs, so a caller that already
    knows the value from scanning the larger original text should redact the
    derived string using that known value directly, not by re-scanning the
    short string."""
    known_values = {EXAMPLE_AWS_ACCESS_KEY}
    short_derived_string = f"heading 'Where does {EXAMPLE_AWS_ACCESS_KEY} live'"

    redacted = redact_known_secret_values(short_derived_string, known_values)

    assert EXAMPLE_AWS_ACCESS_KEY not in redacted
    assert REDACTION_PLACEHOLDER in redacted


def test_redact_known_secret_values_longest_first_avoids_partial_leak():
    """The bug this guards against: redacting a shorter value first would
    destroy a longer value's exact text before its own replacement ran, leaving
    most of the real token exposed in the output. Redaction order must never
    depend on set iteration -- the longer value has to be replaced before a
    shorter value it contains can ever be. In the detect-secrets world the
    scanner itself produced the overlapping pair (a `ghp` prefix match inside
    the full token); here the caller supplies both, as it may when merging
    value sets from more than one scan."""
    token = "ghp_1234567890abcdefghijklmnopqrstuvwxyz12"  # noqa: S105

    redacted = redact_known_secret_values(f'private_token = "{token}"', {"ghp", token})

    assert token not in redacted
    assert "1234567890abcdefghijklmnopqrstuvwxyz12" not in redacted, (
        "most of the real token leaked"
    )
    assert redacted == f'private_token = "{REDACTION_PLACEHOLDER}"'

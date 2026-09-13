"""Redaction helpers for the diagnostics download.

Matching on key *fragments* rather than an exact list of known keys is deliberate: the
diagnostics include the raw API payloads, which is where an unmapped value hides when the
Daitem side changes. A key nobody anticipated must be redacted anyway, not leak because it
was absent from a hardcoded list.

Two levels, because they serve different purposes in a bug report:

- Secrets are replaced outright. They have no diagnostic value.
- Identifiers (serial numbers, names, email) are kept partially. They stay correlatable
  between the panel, its detectors and the raw payload, without publishing the identity of
  someone's home in a public issue.
"""

from __future__ import annotations

from typing import Any

#: Replaced by `***`. `code` covers both the alarm code and the API's `codeIndex`;
#: `sessionid` covers `ttmSessionId` without catching our own `session_busy` flag.
SECRET_KEY_FRAGMENTS = (
    "password",
    "passwd",
    "token",
    "secret",
    "authorization",
    "credential",
    "jwt",
    "code",
    "sessionid",
)

#: Kept as `abc...xyz`: still correlatable across the payload, no longer identifying.
IDENTIFYING_KEY_FRAGMENTS = (
    "serialnumber",
    "username",
    "firstname",
    "lastname",
    "useruid",
    "email",
    "name",
)

#: Raw payloads stay bounded, so a diagnostics file remains attachable to an issue.
MAX_STRING_LENGTH = 512

#: Below this, keeping the ends of a value would give away most of it, so drop it entirely.
MIN_PARTIAL_LENGTH = 6


def _normalize(key: str) -> str:
    return key.lower().replace("_", "").replace("-", "")


def is_secret_key(key: str) -> bool:
    """Whether a key holds something with no place in a bug report."""
    return any(fragment in _normalize(key) for fragment in SECRET_KEY_FRAGMENTS)


def is_identifying_key(key: str) -> bool:
    """Whether a key holds something identifying but useful when partially kept."""
    return any(fragment in _normalize(key) for fragment in IDENTIFYING_KEY_FRAGMENTS)


def partial(value: str) -> str:
    """Keep the ends of a value, enough to correlate it, not enough to identify it."""
    if not value:
        return ""
    if len(value) <= MIN_PARTIAL_LENGTH:
        return "***"
    return f"{value[:3]}...{value[-3:]}"


def redact(value: Any) -> Any:
    """Recursively redact a payload, whatever shape the API returned it in."""
    if isinstance(value, dict):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                redacted[key] = redact(item)
            elif is_secret_key(key):
                redacted[key] = "***"
            elif is_identifying_key(key) and isinstance(item, str):
                redacted[key] = partial(item)
            else:
                redacted[key] = redact(item)
        return redacted
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, set):
        return {redact(item) for item in value}
    if isinstance(value, str) and len(value) > MAX_STRING_LENGTH:
        return f"{value[:256]}...{value[-64:]}"
    return value

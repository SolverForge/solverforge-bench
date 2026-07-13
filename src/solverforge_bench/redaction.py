"""Redact secrets from command arguments before reporting or persistence."""

from __future__ import annotations

from collections.abc import Iterable


REDACTED_VALUE = "<redacted>"
SENSITIVE_VALUE_OPTIONS = frozenset({"--database-url", "--postgres-url"})


def redact_sensitive_command_args(args: Iterable[object]) -> list[str]:
    """Return stringified command arguments with sensitive option values removed."""

    values = [str(value) for value in args]
    redacted: list[str] = []
    redact_next = False
    for value in values:
        if redact_next:
            redacted.append(REDACTED_VALUE)
            redact_next = False
            continue

        option, separator, _ = value.partition("=")
        if option in SENSITIVE_VALUE_OPTIONS:
            if separator:
                redacted.append(f"{option}={REDACTED_VALUE}")
            else:
                redacted.append(value)
                redact_next = True
            continue

        redacted.append(value)
    return redacted

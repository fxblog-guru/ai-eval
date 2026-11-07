"""Mask obvious secrets and personal data before the runner writes evidence to disk.

A run's traces hold whatever the system under evaluation returned, and an adapter that echoes
its own request headers puts the API key in a file that is then uploaded to the report hub. The
patterns below are the shapes that leak in practice; they are deliberately conservative, so a
string that merely looks random is left alone.

    redact(obj) -> (copy of obj with secrets replaced, {kind: count})
"""

from __future__ import annotations

import re
from typing import Any

MASK = "[REDACTED:{kind}]"

# Order matters: the specific key shapes run before the generic bearer/assignment rules, so the
# count names the kind of secret, not just "token".
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{16,}")),
    ("openai-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}")),
    ("aws-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("gitlab-token", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("google-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    ("bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")),
]

# A value stored under one of these keys is a credential whatever it looks like.
SECRET_KEYS = re.compile(r"(?i)^(?:x-)?(?:api[-_]?key|authorization|password|passwd|secret|"
                         r"client[-_]?secret|access[-_]?token|refresh[-_]?token|token)$")


def redact_text(text: str, counts: dict[str, int]) -> str:
    for kind, pattern in PATTERNS:
        text, n = pattern.subn(MASK.format(kind=kind), text)
        if n:
            counts[kind] = counts.get(kind, 0) + n
    return text


def _walk(obj: Any, counts: dict[str, int]) -> Any:
    if isinstance(obj, str):
        return redact_text(obj, counts)
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and SECRET_KEYS.match(k) and isinstance(v, str) and v:
                counts["secret-field"] = counts.get("secret-field", 0) + 1
                out[k] = MASK.format(kind="secret-field")
            else:
                out[k] = _walk(v, counts)
        return out
    if isinstance(obj, (list, tuple)):
        return [_walk(v, counts) for v in obj]
    return obj


def redact(obj: Any) -> tuple[Any, dict[str, int]]:
    """A redacted deep copy of `obj` and how many values of each kind were masked."""
    counts: dict[str, int] = {}
    return _walk(obj, counts), counts

from __future__ import annotations

import re
from dataclasses import dataclass

_SECRET_PATTERNS = [
    re.compile(
        r"(?i)\b(?:api[_ -]?key|token|secret|password|cookie|authorization)\b\s*[:=]\s*([^\s,;]+)"
    ),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{12,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]


@dataclass(frozen=True, slots=True)
class SecretScanResult:
    detected: bool
    sanitized: str
    kinds: tuple[str, ...] = ()


def scan_memory_secrets(text: str) -> SecretScanResult:
    sanitized = text
    kinds: list[str] = []
    for index, pattern in enumerate(_SECRET_PATTERNS):
        if not pattern.search(sanitized):
            continue
        kinds.append(f"secret_pattern_{index + 1}")
        if index == 0:
            sanitized = pattern.sub(lambda match: match.group(0).split(match.group(1))[0] + "<redacted>", sanitized)
        else:
            sanitized = pattern.sub("<redacted>", sanitized)
    return SecretScanResult(
        detected=bool(kinds),
        sanitized=sanitized,
        kinds=tuple(kinds),
    )

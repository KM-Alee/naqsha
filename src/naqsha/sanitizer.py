"""Observation Sanitizer."""

from __future__ import annotations

import re
from dataclasses import dataclass

from naqsha.tools.base import ToolObservation

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s]+"),
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),
]


@dataclass(frozen=True)
class ObservationSanitizer:
    """Redact secret-like content and cap observation size before persistence."""

    max_chars: int = 4000

    def sanitize(self, observation: ToolObservation) -> ToolObservation:
        content = observation.content
        for pattern in SECRET_PATTERNS:
            content = pattern.sub("[REDACTED]", content)
        truncated = len(content) > self.max_chars
        if truncated:
            content = content[: self.max_chars] + "\n[TRUNCATED]"
        metadata = dict(observation.metadata or {})
        if truncated:
            metadata["truncated"] = True
        return ToolObservation(ok=observation.ok, content=content, metadata=metadata)

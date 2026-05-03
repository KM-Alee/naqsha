"""Circuit breaker for consecutive identical tool failures."""

from __future__ import annotations

from naqsha.tools.base import ToolObservation


class CircuitBreakerTrippedError(RuntimeError):
    """Raised when consecutive identical tool failures exceed the configured threshold."""

    def __init__(
        self,
        *,
        tool_name: str,
        consecutive_failures: int,
        message: str = "",
    ) -> None:
        self.tool_name = tool_name
        self.consecutive_failures = consecutive_failures
        text = (
            message
            or f"Circuit breaker tripped for tool {tool_name!r} after "
            f"{consecutive_failures} consecutive identical failure(s)."
        )
        super().__init__(text)


def circuit_failure_threshold(max_retries_config: int) -> int:
    """
    Number of consecutive identical failures required to trip.

    Values <= 0 mean trip on the first failure (never unlimited retries).
    """

    return 1 if max_retries_config <= 0 else max_retries_config


def _failure_signature(observation: ToolObservation) -> tuple[str, str]:
    if observation.ok:
        return ("", "")
    meta = observation.metadata or {}
    err_kind = meta.get("error")
    kind = err_kind if isinstance(err_kind, str) else repr(err_kind)
    return (kind, observation.content)


class CircuitBreaker:
    """
    Tracks consecutive identical failed tool observations per tool name.

    A successful observation clears the streak for that tool. A failed observation
    that differs from the previous failure signature resets the streak to 1.
    """

    def __init__(self, max_consecutive_failures: int) -> None:
        if max_consecutive_failures < 1:
            raise ValueError("max_consecutive_failures must be >= 1.")
        self._max = max_consecutive_failures
        self._signature: dict[str, tuple[str, str]] = {}
        self._count: dict[str, int] = {}

    def record(self, tool_name: str, observation: ToolObservation) -> int:
        """Update state from one tool outcome. Returns current streak after update."""

        if observation.ok:
            self._signature.pop(tool_name, None)
            self._count.pop(tool_name, None)
            return 0

        sig = _failure_signature(observation)
        if self._signature.get(tool_name) == sig:
            self._count[tool_name] = self._count.get(tool_name, 0) + 1
        else:
            self._signature[tool_name] = sig
            self._count[tool_name] = 1
        return self._count.get(tool_name, 0)

    def streak(self, tool_name: str) -> int:
        return self._count.get(tool_name, 0)

    def should_trip(self, tool_name: str) -> bool:
        return self.streak(tool_name) >= self._max

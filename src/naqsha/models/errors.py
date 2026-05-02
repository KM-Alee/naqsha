"""Shared errors for remote Model Client adapters."""


class ModelInvocationError(RuntimeError):
    """Raised when transport or provider payloads cannot yield a valid NAP message."""

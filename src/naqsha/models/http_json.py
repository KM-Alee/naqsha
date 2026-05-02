"""Stdlib JSON POST helpers for provider adapters."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from naqsha.models.errors import ModelInvocationError

_PostFn = Callable[[str, dict[str, str], bytes, float], tuple[int, bytes]]

_SECRETISH_HEADER_KEYS = frozenset(
    {
        "authorization",
        "api-key",
        "x-api-key",
        "x-goog-api-key",
    }
)


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in headers.items():
        lk = key.lower()
        if lk in _SECRETISH_HEADER_KEYS or "token" in lk:
            out[key] = "<redacted>"
        else:
            out[key] = value
    return out


def default_post(
    url: str,
    headers: dict[str, str],
    body: bytes,
    timeout: float,
) -> tuple[int, bytes]:
    req = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            code = getattr(resp, "status", None) or resp.getcode()
            return int(code), resp.read()
    except HTTPError as exc:
        return exc.code, exc.read()


def post_json(
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: float,
    post_fn: _PostFn | None = None,
    error_label: str = "Provider",
) -> dict[str, Any]:
    """POST JSON, parse the body as an object, and map failures to ``ModelInvocationError``."""

    fn = post_fn or default_post
    send_headers = {**headers, "Content-Type": "application/json"}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    status, data = fn(url, send_headers, raw, timeout_seconds)

    try:
        parsed: Any = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ModelInvocationError(
            f"{error_label} returned non-JSON body (HTTP {status})."
        ) from exc

    if not isinstance(parsed, dict):
        raise ModelInvocationError(f"{error_label} JSON root must be an object.")

    if status < 200 or status >= 300:
        detail = _provider_error_detail(parsed)
        raise ModelInvocationError(
            f"{error_label} HTTP {status}: {detail} "
            f"(request headers: {redact_headers(send_headers)})"
        )

    return parsed


def _provider_error_detail(parsed: dict[str, Any]) -> str:
    if parsed.get("type") == "error":
        inner = parsed.get("error")
        if isinstance(inner, dict):
            msg = inner.get("message")
            if isinstance(msg, str):
                return msg
            return repr(inner)
    err = parsed.get("error")
    if isinstance(err, dict):
        msg = err.get("message")
        if isinstance(msg, str):
            return msg
        return repr(err)
    if isinstance(err, str):
        return err
    return repr(parsed)

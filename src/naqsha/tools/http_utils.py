"""Dependency-light HTTP helpers (stdlib only) for starter web tools."""

from __future__ import annotations

import json as jsonlib
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class HttpFetchResult:
    ok: bool
    status_code: int | None
    body_text: str
    truncated_bytes: bool
    error: str | None = None


def is_allowed_http_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if not parsed.netloc:
        return False
    return True


def fetch_http_text(
    url: str,
    *,
    timeout_seconds: float,
    max_body_bytes: int,
    user_agent: str = "naqsha-web-fetch/0.1 (+https://github.com/naqsha)",
) -> HttpFetchResult:
    if not is_allowed_http_url(url):
        return HttpFetchResult(
            ok=False,
            status_code=None,
            body_text="",
            truncated_bytes=False,
            error="Only http and https URLs with a host are allowed.",
        )

    req = Request(url, headers={"User-Agent": user_agent})
    try:
        with urlopen(req, timeout=timeout_seconds) as resp:
            code = getattr(resp, "status", None) or resp.getcode()
            raw = resp.read(max_body_bytes + 1)
    except HTTPError as exc:
        try:
            chunk = exc.read(max_body_bytes + 1)
        except Exception:
            chunk = b""
        truncated = len(chunk) > max_body_bytes
        body = chunk[:max_body_bytes] if truncated else chunk
        text = _bytes_to_text(body)
        return HttpFetchResult(
            ok=False,
            status_code=exc.code,
            body_text=text,
            truncated_bytes=truncated,
            error=f"HTTP error {exc.code}: {exc.reason}",
        )
    except URLError as exc:
        return HttpFetchResult(
            ok=False,
            status_code=None,
            body_text="",
            truncated_bytes=False,
            error=f"URL error: {exc.reason}",
        )
    except TimeoutError:
        return HttpFetchResult(
            ok=False,
            status_code=None,
            body_text="",
            truncated_bytes=False,
            error="Request timed out.",
        )
    except OSError as exc:
        return HttpFetchResult(
            ok=False,
            status_code=None,
            body_text="",
            truncated_bytes=False,
            error=f"Fetch failed: {exc}",
        )

    truncated = len(raw) > max_body_bytes
    chunk = raw[:max_body_bytes] if truncated else raw
    text = _bytes_to_text(chunk)
    return HttpFetchResult(
        ok=True,
        status_code=code if isinstance(code, int) else None,
        body_text=text,
        truncated_bytes=truncated,
        error=None,
    )


def _bytes_to_text(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")


def ddg_instant_answer_json(*, query: str, timeout_seconds: float) -> dict[str, Any]:
    """Call DuckDuckGo Instant Answer API (returns parsed JSON or empty dict on failure)."""

    q = quote_plus(query, safe="")
    url = f"https://api.duckduckgo.com/?q={q}&format=json&no_html=1&skip_disambig=1"
    req = Request(url, headers={"User-Agent": "naqsha-web-search/0.1"})
    try:
        with urlopen(req, timeout=timeout_seconds) as resp:
            raw = resp.read(1_000_000)
    except (HTTPError, URLError, TimeoutError, OSError):
        return {}
    try:
        data = jsonlib.loads(raw.decode("utf-8"))
    except (jsonlib.JSONDecodeError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def format_instant_answer(data: dict[str, Any], *, max_topics: int) -> str:
    lines: list[str] = []
    abs_text = data.get("AbstractText")
    if isinstance(abs_text, str) and abs_text.strip():
        lines.append(abs_text.strip())
        src = data.get("AbstractURL")
        if isinstance(src, str) and src:
            lines.append(f"Source: {src}")
    defin = data.get("Definition")
    if isinstance(defin, str) and defin.strip():
        lines.append(f"Definition: {defin.strip()}")

    topics = data.get("RelatedTopics")
    if isinstance(topics, list) and topics:
        shown = 0
        for item in topics:
            if shown >= max_topics:
                break
            if isinstance(item, dict) and "Text" in item:
                t = item.get("Text")
                if isinstance(t, str) and t.strip():
                    lines.append(t.strip())
                    shown += 1
            elif isinstance(item, dict) and "Topics" in item:
                sub = item.get("Topics")
                if isinstance(sub, list):
                    for subitem in sub:
                        if shown >= max_topics:
                            break
                        if isinstance(subitem, dict):
                            t = subitem.get("Text")
                            if isinstance(t, str) and t.strip():
                                lines.append(t.strip())
                                shown += 1

    answer = data.get("Answer")
    if isinstance(answer, str) and answer.strip():
        lines.insert(0, answer.strip())

    if not lines:
        return ""
    return "\n".join(lines)

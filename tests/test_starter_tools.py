"""Phase 4: Starter Tool Set — schema, success, errors, policy tier, sanitizer boundary."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from naqsha.policy import PolicyDecisionKind, ToolPolicy
from naqsha.protocols.nap import ToolCall
from naqsha.sanitizer import ObservationSanitizer
from naqsha.tools.http_utils import HttpFetchResult
from naqsha.tools.starter import (
    calculator_tool,
    human_approval_tool,
    json_patch_tool,
    read_file_tool,
    run_shell_tool,
    starter_tools,
    web_fetch_tool,
    web_search_tool,
    write_file_tool,
)


def test_calculator_schema_and_success() -> None:
    t = calculator_tool()
    obs = t.execute({"expression": "2 + 2"})
    assert obs.ok and obs.content == "4.0"


def test_calculator_rejects_unsupported_expression() -> None:
    t = calculator_tool()
    with pytest.raises(ValueError, match="Unsupported"):
        t.execute({"expression": "foo()"})


def test_read_file_success_and_root_escape(tmp_path: Path) -> None:
    t = read_file_tool(tmp_path)
    (tmp_path / "hi.txt").write_text("hello", encoding="utf-8")
    assert t.execute({"path": "hi.txt"}).content == "hello"
    bad = t.execute({"path": "../etc/passwd"})
    assert not bad.ok and "root" in bad.content.lower()


def test_read_file_rejects_binary(tmp_path: Path) -> None:
    t = read_file_tool(tmp_path)
    p = tmp_path / "b.bin"
    p.write_bytes(b"\x00\x01\x02")
    obs = t.execute({"path": "b.bin"})
    assert not obs.ok and "binary" in obs.content.lower()


def test_read_file_rejects_oversize(tmp_path: Path) -> None:
    t = read_file_tool(tmp_path)
    (tmp_path / "big.txt").write_text("x" * 100, encoding="utf-8")
    obs = t.execute({"path": "big.txt", "max_bytes": 10})
    assert not obs.ok and "exceeds" in obs.content.lower()


def test_write_file_requires_overwrite(tmp_path: Path) -> None:
    t = write_file_tool(tmp_path)
    (tmp_path / "e.txt").write_text("old", encoding="utf-8")
    first = t.execute({"path": "e.txt", "content": "new"})
    assert not first.ok and "overwrite" in first.content.lower()
    second = t.execute({"path": "e.txt", "content": "new", "overwrite": True})
    assert second.ok
    assert (tmp_path / "e.txt").read_text(encoding="utf-8") == "new"


def test_write_file_policy_tier(tmp_path: Path) -> None:
    tools = starter_tools(tmp_path)
    policy = ToolPolicy.allow_all_starter_tools(tools)
    d = policy.decide(
        ToolCall(id="w", name="write_file", arguments={"path": "a.txt", "content": "x"}),
        tools,
    )
    assert d.decision == PolicyDecisionKind.REQUIRE_APPROVAL


def test_web_fetch_wraps_delimited_untrusted_text(tmp_path: Path) -> None:
    t = web_fetch_tool()
    fake = HttpFetchResult(
        ok=True,
        status_code=200,
        body_text="<p>hi</p>",
        truncated_bytes=False,
        error=None,
    )
    with patch("naqsha.tools.starter.fetch_http_text", return_value=fake):
        obs = t.execute({"url": "https://example.com/p"})
    assert obs.ok
    assert "UNTRUSTED WEB CONTENT" in obs.content
    assert "<p>hi</p>" in obs.content


def test_web_fetch_rejects_non_http_scheme() -> None:
    t = web_fetch_tool()
    obs = t.execute({"url": "file:///etc/passwd"})
    assert not obs.ok
    assert "http" in obs.content.lower()


def test_web_search_formats_stubbed_instant_answer() -> None:
    t = web_search_tool()
    stub = {"AbstractText": "Summary text", "AbstractURL": "https://example.com"}
    with patch("naqsha.tools.starter.ddg_instant_answer_json", return_value=stub):
        obs = t.execute({"query": "test query"})
    assert obs.ok
    assert "UNTRUSTED WEB SEARCH" in obs.content
    assert "Summary text" in obs.content


def test_web_search_empty_query_error() -> None:
    t = web_search_tool()
    obs = t.execute({"query": "   "})
    assert not obs.ok


def test_run_shell_echo(tmp_path: Path) -> None:
    t = run_shell_tool(tmp_path)
    obs = t.execute(
        {"argv": [sys.executable, "-c", "print('hi')"], "cwd": "."},
    )
    assert obs.ok and "hi" in obs.content


def test_run_shell_nonzero_is_structured_error(tmp_path: Path) -> None:
    t = run_shell_tool(tmp_path)
    obs = t.execute(
        {
            "argv": [sys.executable, "-c", "import sys; sys.exit(7)"],
            "cwd": ".",
        },
    )
    assert not obs.ok
    assert "Exit code 7" in obs.content


def test_run_shell_cwd_must_stay_under_root(tmp_path: Path) -> None:
    t = run_shell_tool(tmp_path)
    obs = t.execute({"argv": [sys.executable, "-c", "pass"], "cwd": ".."})
    assert not obs.ok and "root" in obs.content.lower()


def test_run_shell_requires_high_tier_approval(tmp_path: Path) -> None:
    tools = starter_tools(tmp_path)
    policy = ToolPolicy.allow_all_starter_tools(tools)
    d = policy.decide(
        ToolCall(
            id="s",
            name="run_shell",
            arguments={"argv": [sys.executable, "-c", "pass"], "cwd": "."},
        ),
        tools,
    )
    assert d.decision == PolicyDecisionKind.REQUIRE_APPROVAL


def test_json_patch_validates_before_write(tmp_path: Path) -> None:
    t = json_patch_tool(tmp_path)
    p = tmp_path / "data.json"
    p.write_text(json.dumps({"a": 1, "b": {"c": 2}}), encoding="utf-8")
    patch_doc = json.dumps(
        [
            {"op": "test", "path": "/a", "value": 99},
            {"op": "replace", "path": "/a", "value": 3},
        ]
    )
    obs = t.execute({"path": "data.json", "patch_json": patch_doc})
    assert not obs.ok and "test failed" in obs.content.lower()
    assert json.loads(p.read_text(encoding="utf-8")) == {"a": 1, "b": {"c": 2}}


def test_json_patch_applies_atomically(tmp_path: Path) -> None:
    t = json_patch_tool(tmp_path)
    p = tmp_path / "data.json"
    p.write_text(json.dumps({"x": 0}), encoding="utf-8")
    patch_doc = json.dumps([{"op": "replace", "path": "/x", "value": 42}])
    obs = t.execute({"path": "data.json", "patch_json": patch_doc})
    assert obs.ok
    assert json.loads(p.read_text(encoding="utf-8")) == {"x": 42}
    assert not (tmp_path / "data.json.naqsha.tmp").exists()


def test_json_patch_invalid_json_in_file(tmp_path: Path) -> None:
    t = json_patch_tool(tmp_path)
    p = tmp_path / "bad.json"
    p.write_text("{", encoding="utf-8")
    obs = t.execute({"path": "bad.json", "patch_json": "[]"})
    assert not obs.ok and "valid JSON" in obs.content


def test_human_approval_records_reason() -> None:
    t = human_approval_tool()
    obs = t.execute({"reason": "because"})
    assert obs.ok and "because" in obs.content and "Approval Gate" in obs.content


def test_starter_observations_sanitized(tmp_path: Path) -> None:
    t = read_file_tool(tmp_path)
    (tmp_path / "s.txt").write_text("token=sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", encoding="utf-8")
    raw = t.execute({"path": "s.txt"})
    san = ObservationSanitizer(max_chars=4000)
    sanitized = san.sanitize(raw)
    assert "sk-" not in sanitized.content.lower()

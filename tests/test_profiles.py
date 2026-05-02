"""Tests for Run Profile parsing and filesystem resolution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from naqsha.profiles import ProfileValidationError, load_run_profile, parse_run_profile


def test_anthropic_profile_defaults(tmp_path: Path) -> None:
    profile = parse_run_profile(
        {"name": "a", "model": "anthropic", "trace_dir": ".", "tool_root": "."},
        base_dir=tmp_path,
    )
    assert profile.anthropic is not None
    assert profile.anthropic.api_key_env == "ANTHROPIC_API_KEY"
    assert profile.anthropic.max_tokens == 4096


def test_gemini_profile_defaults(tmp_path: Path) -> None:
    profile = parse_run_profile(
        {"name": "g", "model": "gemini", "trace_dir": ".", "tool_root": "."},
        base_dir=tmp_path,
    )
    assert profile.gemini is not None
    assert "generativelanguage" in profile.gemini.base_url


def test_fake_model_with_anthropic_adapter_rejected(tmp_path: Path) -> None:
    with pytest.raises(ProfileValidationError, match="fake_model"):
        parse_run_profile(
            {
                "name": "x",
                "model": "anthropic",
                "trace_dir": ".",
                "tool_root": ".",
                "fake_model": {"messages": [{"kind": "answer", "text": "x"}]},
            },
            base_dir=tmp_path,
        )


def test_relative_paths_resolve_against_profile_file_directory(tmp_path: Path) -> None:
    sub = tmp_path / "proj"
    sub.mkdir()
    trace_dir_name = "traces_here"
    (sub / trace_dir_name).mkdir()
    profile_path = sub / "my.json"
    profile_path.write_text(
        json.dumps(
            {
                "name": "rel",
                "model": "fake",
                "trace_dir": trace_dir_name,
                "tool_root": ".",
            }
        ),
        encoding="utf-8",
    )
    profile = load_run_profile(str(profile_path))
    assert profile.trace_dir == (sub / trace_dir_name).resolve()
    assert profile.tool_root == sub.resolve()


def test_openai_compat_profile_loads_with_defaults(tmp_path: Path) -> None:
    p = tmp_path / "o.json"
    p.write_text(
        json.dumps({"name": "x", "model": "openai_compat", "trace_dir": ".", "tool_root": "."}),
        encoding="utf-8",
    )
    profile = load_run_profile(str(p))
    assert profile.model == "openai_compat"
    assert profile.openai_compat is not None
    assert profile.openai_compat.base_url == "https://api.openai.com/v1"
    assert profile.openai_compat.api_key_env == "OPENAI_API_KEY"


def test_openai_compat_hyphen_normalized(tmp_path: Path) -> None:
    profile = parse_run_profile(
        {"name": "h", "model": "openai-compat", "trace_dir": ".", "tool_root": "."},
        base_dir=tmp_path,
    )
    assert profile.model == "openai_compat"


def test_openai_compat_section_rejected_when_model_fake(tmp_path: Path) -> None:
    with pytest.raises(ProfileValidationError, match="only valid when model"):
        parse_run_profile(
            {
                "name": "x",
                "model": "fake",
                "trace_dir": ".",
                "tool_root": ".",
                "openai_compat": {"model": "gpt-4o-mini"},
            },
            base_dir=tmp_path,
        )


def test_fake_model_with_openai_adapter_rejected(tmp_path: Path) -> None:
    with pytest.raises(ProfileValidationError, match="fake_model"):
        parse_run_profile(
            {
                "name": "x",
                "model": "openai_compat",
                "trace_dir": ".",
                "tool_root": ".",
                "fake_model": {"messages": [{"kind": "answer", "text": "x"}]},
            },
            base_dir=tmp_path,
        )


def test_openai_compat_unknown_nested_key_rejected(tmp_path: Path) -> None:
    with pytest.raises(ProfileValidationError, match="Unknown openai_compat"):
        parse_run_profile(
            {
                "name": "x",
                "model": "openai_compat",
                "trace_dir": ".",
                "tool_root": ".",
                "openai_compat": {"nope": 1},
            },
            base_dir=tmp_path,
        )


def test_simplemem_cross_profile_loads_and_resolves_paths(tmp_path: Path) -> None:
    explicit_db = tmp_path / "explicit.sqlite"
    p = tmp_path / "cross.json"
    p.write_text(
        json.dumps(
            {
                "name": "with-cross",
                "model": "fake",
                "trace_dir": ".",
                "tool_root": ".",
                "memory_adapter": "simplemem_cross",
                "memory_cross_project": "unit-test-project",
                "memory_cross_database": str(explicit_db.name),
            }
        ),
        encoding="utf-8",
    )
    profile = load_run_profile(str(p))
    assert profile.memory_adapter == "simplemem_cross"
    assert profile.memory_cross_project == "unit-test-project"
    assert profile.memory_cross_database == explicit_db.resolve()


def test_memory_adapter_hyphen_normalized(tmp_path: Path) -> None:
    profile = parse_run_profile(
        {
            "name": "hyphen-cross",
            "model": "fake",
            "trace_dir": ".",
            "tool_root": ".",
            "memory_adapter": "simplemem-cross",
        },
        base_dir=tmp_path,
    )
    assert profile.memory_adapter == "simplemem_cross"


def test_toml_round_trip_via_load_run_profile(tmp_path: Path) -> None:
    p = tmp_path / "f.toml"
    p.write_bytes(
        b'name = "from-toml"\n'
        b'model = "fake"\n'
        b'trace_dir = ".rel-traces"\n'
        b'tool_root = "."\n'
        b'sanitizer_max_chars = 2000\n'
        b"\n[budgets]\n"
        b"max_steps = 5\n",
    )
    profile = load_run_profile(str(p))
    assert profile.name == "from-toml"
    assert profile.budgets.max_steps == 5
    assert profile.sanitizer_max_chars == 2000


def test_unknown_extra_top_level_keys_rejected(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text(
        json.dumps({"name": "x", "model": "fake", "extra_field": True}),
        encoding="utf-8",
    )
    with pytest.raises(ProfileValidationError, match="Unknown profile keys"):
        load_run_profile(str(p))


def test_allowed_tools_must_reference_starter_names(tmp_path: Path) -> None:
    p = tmp_path / "bad-tools.json"
    p.write_text(
        json.dumps(
            {
                "name": "x",
                "model": "fake",
                "allowed_tools": ["not_a_tool"],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ProfileValidationError, match="Unknown starter tool names"):
        load_run_profile(str(p))


def test_fake_model_messages_must_parse_as_nap(tmp_path: Path) -> None:
    with pytest.raises(ProfileValidationError, match="Unexpected NAP fields"):
        parse_run_profile(
            {
                "name": "x",
                "model": "fake",
                "fake_model": {"messages": [{"kind": "answer", "text": "", "illegal": True}]},
            },
            base_dir=tmp_path,
        )


def test_budgets_unknown_key_rejected(tmp_path: Path) -> None:
    with pytest.raises(ProfileValidationError, match="Unknown budgets keys"):
        parse_run_profile(
            {"name": "x", "model": "fake", "budgets": {"nope": 1}},
            base_dir=tmp_path,
        )

"""Run Profile configuration and loaders for JSON/TOML files."""

from __future__ import annotations

import json
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from importlib.resources import files
from pathlib import Path
from typing import Any

from naqsha.budgets import BudgetLimits
from naqsha.protocols.nap import NapValidationError, parse_nap_message
from naqsha.tools.base import RiskTier
from naqsha.tools.starter import starter_tool_names


class ProfileValidationError(ValueError):
    """Profile file violates schema or contradicts adapter availability."""


@dataclass(frozen=True)
class RunProfile:
    """Named runtime choices for model, tools, memory, traces, approvals, budgets."""

    name: str = "local"
    trace_dir: Path = Path(".naqsha/traces")
    tool_root: Path = Path(".")
    model: str = "fake"
    allowed_tool_names: frozenset[str] | None = None
    memory_adapter: str = "none"
    memory_token_budget: int = 512
    memory_cross_project: str = "default"
    memory_cross_database: Path = Path(".naqsha/simplemem-cross.sqlite")
    auto_approve: bool = False
    approval_required_tiers: frozenset[RiskTier] = field(
        default_factory=lambda: frozenset({RiskTier.WRITE, RiskTier.HIGH})
    )
    budgets: BudgetLimits = field(default_factory=BudgetLimits)
    sanitizer_max_chars: int = 4000
    fake_model_messages: tuple[dict[str, Any], ...] | None = None


DEFAULT_FAKE_SCRIPT: tuple[dict[str, Any], ...] = (
    {"kind": "action", "calls": [{"id": "clock-1", "name": "clock", "arguments": {}}]},
    {"kind": "answer", "text": "Local fake-model run completed."},
)


_BUNDLED_PKG = "naqsha.bundled_profiles"


def _read_mapping_from_path(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    raw = path.read_bytes()
    if suffix == ".json":
        data = json.loads(raw.decode("utf-8"))
    elif suffix == ".toml":
        data = tomllib.loads(raw.decode("utf-8"))
    else:
        raise ProfileValidationError(
            f"Unsupported profile suffix {suffix!r}; use '.json' or '.toml'."
        )
    if not isinstance(data, dict):
        raise ProfileValidationError("Profile root must be a JSON object or TOML table.")
    return data


def _read_mapping_bundled(name: str) -> dict[str, Any] | None:
    root = files(_BUNDLED_PKG)
    for ext, loader in (
        (".json", lambda b: json.loads(b.decode("utf-8"))),
        (".toml", lambda b: tomllib.loads(b.decode("utf-8"))),
    ):
        candidate = root / f"{name}{ext}"
        if candidate.is_file():
            parsed = loader(candidate.read_bytes())
            if isinstance(parsed, dict):
                return parsed
            raise ProfileValidationError(f"Bundled profile {name!r} root must be an object/table.")
    return None


def load_raw_profile(spec: str) -> tuple[dict[str, Any], Path]:
    """Load a profile from a filesystem path or bundled name.

    Returns the parsed mapping and the directory used to resolve relative paths inside
    the profile (parent of the profile file, or cwd for bundled profiles).
    """

    cwd = Path.cwd()
    trimmed = spec.strip()
    if not trimmed:
        raise ProfileValidationError("Profile specifier must not be empty.")

    path = Path(trimmed).expanduser()
    if path.is_file():
        resolved = path.resolve()
        return _read_mapping_from_path(resolved), resolved.parent

    for candidate in (
        cwd / "profiles" / f"{trimmed}.json",
        cwd / "profiles" / f"{trimmed}.toml",
        cwd / "examples" / "profiles" / f"{trimmed}.json",
        cwd / "examples" / "profiles" / f"{trimmed}.toml",
        cwd / "docs" / "examples" / "profiles" / f"{trimmed}.json",
        cwd / "docs" / "examples" / "profiles" / f"{trimmed}.toml",
    ):
        if candidate.is_file():
            resolved = candidate.resolve()
            return _read_mapping_from_path(resolved), resolved.parent

    bundled = _read_mapping_bundled(trimmed)
    if bundled is not None:
        return bundled, cwd

    raise ProfileValidationError(
        f"Profile {trimmed!r} not found. Pass a path to a .json/.toml file, a name matching "
        f"a bundled profile, or files under profiles/, examples/profiles/, or "
        f"docs/examples/profiles/ in the working directory."
    )


def _as_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ProfileValidationError(f"Field {field_name!r} must be a boolean.")


def _as_str(value: Any, field_name: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ProfileValidationError(f"Field {field_name!r} must be a non-empty string.")




def _as_int(value: Any, field_name: str, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProfileValidationError(f"Field {field_name!r} must be an integer.")
    if value < minimum:
        raise ProfileValidationError(f"Field {field_name!r} must be >= {minimum}.")
    return value


def _as_positive_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ProfileValidationError(f"Field {field_name!r} must be a number.")
    f = float(value)
    if f <= 0:
        raise ProfileValidationError(f"Field {field_name!r} must be positive.")
    return f


def _resolve_path(raw: Any, field_name: str, base_dir: Path) -> Path:
    text = _as_str(raw, field_name)
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    else:
        path = path.resolve()
    return path


def _parse_budgets(blob: Any) -> BudgetLimits:
    if blob is None:
        return BudgetLimits()
    if not isinstance(blob, Mapping):
        raise ProfileValidationError("'budgets' must be an object/table.")
    kwargs: dict[str, Any] = {}
    if "max_steps" in blob:
        kwargs["max_steps"] = _as_int(blob["max_steps"], "budgets.max_steps", minimum=1)
    if "max_tool_calls" in blob:
        kwargs["max_tool_calls"] = _as_int(
            blob["max_tool_calls"], "budgets.max_tool_calls", minimum=1
        )
    if "wall_clock_seconds" in blob:
        kwargs["wall_clock_seconds"] = _as_positive_float(
            blob["wall_clock_seconds"], "budgets.wall_clock_seconds"
        )
    if "per_tool_seconds" in blob:
        kwargs["per_tool_seconds"] = _as_positive_float(
            blob["per_tool_seconds"], "budgets.per_tool_seconds"
        )
    if "max_model_tokens" in blob:
        m = blob["max_model_tokens"]
        if m is None:
            kwargs["max_model_tokens"] = None
        elif isinstance(m, bool) or not isinstance(m, int):
            raise ProfileValidationError("budgets.max_model_tokens must be an integer or null.")
        elif m < 1:
            raise ProfileValidationError("budgets.max_model_tokens must be >= 1 when set.")
        else:
            kwargs["max_model_tokens"] = m
    unknown = set(blob) - {
        "max_steps",
        "max_tool_calls",
        "wall_clock_seconds",
        "per_tool_seconds",
        "max_model_tokens",
    }
    if unknown:
        raise ProfileValidationError(f"Unknown budgets keys: {sorted(unknown)}")
    defaults = BudgetLimits()
    return BudgetLimits(
        max_steps=int(kwargs.get("max_steps", defaults.max_steps)),
        max_tool_calls=int(kwargs.get("max_tool_calls", defaults.max_tool_calls)),
        wall_clock_seconds=float(kwargs.get("wall_clock_seconds", defaults.wall_clock_seconds)),
        per_tool_seconds=float(kwargs.get("per_tool_seconds", defaults.per_tool_seconds)),
        max_model_tokens=kwargs.get("max_model_tokens", defaults.max_model_tokens),
    )


def _parse_risk_tiers(raw: Any) -> frozenset[RiskTier]:
    if raw is None:
        return frozenset({RiskTier.WRITE, RiskTier.HIGH})
    if not isinstance(raw, list) or not raw:
        raise ProfileValidationError("'approval_required_tiers' must be a non-empty array.")
    out: list[RiskTier] = []
    for item in raw:
        if not isinstance(item, str):
            raise ProfileValidationError("Each approval tier must be a string.")
        try:
            out.append(RiskTier(item))
        except ValueError as exc:
            valid = ", ".join(repr(t.value) for t in RiskTier)
            raise ProfileValidationError(
                f"Unknown risk tier {item!r}; expected one of {valid}."
            ) from exc
    return frozenset(out)


def _validate_fake_messages(raw: Any) -> tuple[dict[str, Any], ...] | None:
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise ProfileValidationError("'fake_model.messages' must be an array.")
    validated: list[dict[str, Any]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ProfileValidationError(f"fake_model.messages[{i}] must be an object.")
        try:
            parse_nap_message(item)
        except NapValidationError as exc:
            raise ProfileValidationError(f"fake_model.messages[{i}]: {exc}") from exc
        validated.append(item)
    return tuple(validated)


def parse_run_profile(data: Mapping[str, Any], *, base_dir: Path) -> RunProfile:
    """Build a RunProfile from a mapping; validate fields and coerce paths."""

    known = {f.name for f in fields(RunProfile)} | {
        "budgets",
        "fake_model",
        "allowed_tools",
    }
    extra = set(data) - known
    if extra:
        raise ProfileValidationError(f"Unknown profile keys: {sorted(extra)}.")

    name = _as_str(data.get("name", "unnamed"), "name")
    model = _as_str(data.get("model", "fake"), "model")
    if model == "openai_compat":
        raise ProfileValidationError(
            "Model adapter 'openai_compat' is not available yet. "
            "Use 'fake' for local runs until the provider adapter lands (Phase 6)."
        )
    if model != "fake":
        raise ProfileValidationError(
            f"Unsupported model {model!r}. Supported values: 'fake', 'openai_compat' "
            "(openai_compat is deferred)."
        )

    trace_dir = _resolve_path(data.get("trace_dir", ".naqsha/traces"), "trace_dir", base_dir)
    tool_root = _resolve_path(data.get("tool_root", "."), "tool_root", base_dir)

    allowed_raw = data.get("allowed_tools")
    allowed_tool_names: frozenset[str] | None
    if allowed_raw is None:
        allowed_tool_names = None
    elif isinstance(allowed_raw, list):
        if not allowed_raw:
            raise ProfileValidationError("'allowed_tools' must not be empty when provided.")
        names = starter_tool_names()
        seen: list[str] = []
        unknown: list[str] = []
        for item in allowed_raw:
            tool_name = _as_str(item, "allowed_tools[]")
            if tool_name not in names:
                unknown.append(tool_name)
            seen.append(tool_name)
        if unknown:
            raise ProfileValidationError(
                "Unknown starter tool names in allowed_tools: "
                f"{sorted(set(unknown))}. Valid names: {sorted(names)}."
            )
        allowed_tool_names = frozenset(seen)
    else:
        raise ProfileValidationError("'allowed_tools' must be null or an array.")

    memory_adapter = (
        _as_str(data.get("memory_adapter", "none"), "memory_adapter")
        .strip()
        .lower()
        .replace("-", "_")
    )
    memory_cross_project = _as_str(
        data.get("memory_cross_project", "default"),
        "memory_cross_project",
    )
    memory_cross_database = _resolve_path(
        data.get("memory_cross_database", ".naqsha/simplemem-cross.sqlite"),
        "memory_cross_database",
        base_dir,
    )

    if memory_adapter not in {"none", "inmemory", "simplemem_cross"}:
        raise ProfileValidationError(
            "memory_adapter must be 'none', 'inmemory', or 'simplemem_cross'; "
            f"got {memory_adapter!r}."
        )

    memory_token_budget = _as_int(data.get("memory_token_budget", 512), "memory_token_budget")

    fake_messages: tuple[dict[str, Any], ...] | None = None
    fake_blob = data.get("fake_model")
    if fake_blob is not None:
        if not isinstance(fake_blob, Mapping):
            raise ProfileValidationError("'fake_model' must be an object/table.")
        extra_fm = set(fake_blob) - {"messages"}
        if extra_fm:
            raise ProfileValidationError(f"Unknown fake_model keys: {sorted(extra_fm)}.")
        fake_messages = _validate_fake_messages(fake_blob.get("messages"))

    auto_approve = _as_bool(data.get("auto_approve", False), "auto_approve")
    approval_required_tiers = _parse_risk_tiers(data.get("approval_required_tiers"))

    budgets = _parse_budgets(data.get("budgets"))
    sanitizer_max_chars = _as_int(data.get("sanitizer_max_chars", 4000), "sanitizer_max_chars")

    return RunProfile(
        name=name,
        trace_dir=trace_dir,
        tool_root=tool_root,
        model=model,
        allowed_tool_names=allowed_tool_names,
        memory_adapter=memory_adapter,
        memory_token_budget=memory_token_budget,
        memory_cross_project=memory_cross_project,
        memory_cross_database=memory_cross_database,
        auto_approve=auto_approve,
        approval_required_tiers=approval_required_tiers,
        budgets=budgets,
        sanitizer_max_chars=sanitizer_max_chars,
        fake_model_messages=fake_messages,
    )


def load_run_profile(spec: str) -> RunProfile:
    """Resolve `spec`, load JSON/TOML, and validate into a RunProfile."""

    raw, base_dir = load_raw_profile(spec)
    return parse_run_profile(raw, base_dir=base_dir)


def describe_profile_dict(profile: RunProfile) -> dict[str, Any]:
    """JSON-serializable profile summary without Path objects."""

    return {
        "name": profile.name,
        "model": profile.model,
        "trace_dir": str(profile.trace_dir),
        "tool_root": str(profile.tool_root),
        "allowed_tools": sorted(profile.allowed_tool_names)
        if profile.allowed_tool_names
        else None,
        "memory_adapter": profile.memory_adapter,
        "memory_token_budget": profile.memory_token_budget,
        "memory_cross_project": profile.memory_cross_project,
        "memory_cross_database": str(profile.memory_cross_database),
        "auto_approve": profile.auto_approve,
        "approval_required_tiers": sorted(t.value for t in profile.approval_required_tiers),
        "budgets": {
            "max_steps": profile.budgets.max_steps,
            "max_tool_calls": profile.budgets.max_tool_calls,
            "wall_clock_seconds": profile.budgets.wall_clock_seconds,
            "per_tool_seconds": profile.budgets.per_tool_seconds,
            "max_model_tokens": profile.budgets.max_model_tokens,
        },
        "sanitizer_max_chars": profile.sanitizer_max_chars,
        "fake_model_scripted_messages": profile.fake_model_messages is not None,
    }

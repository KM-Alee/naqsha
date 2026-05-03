"""Parse and validate Team Workspace topology from ``naqsha.toml``."""

from __future__ import annotations

import json
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from naqsha.budgets import BudgetLimits
from naqsha.memory.sharing import TeamMemoryConfig
from naqsha.models.nap import NapValidationError, parse_nap_message
from naqsha.profiles import ProfileValidationError
from naqsha.tools.base import RiskTier
from naqsha.tools.starter import starter_tool_names

MEMORY_DECORATED_TOOL_NAMES = frozenset({"memory_schema", "list_memory_tables"})


def _safe_delegate_tool_name(agent_id: str) -> str:
    safe = "".join(ch if ch.isalnum() else "_" for ch in agent_id)
    return f"delegate_to_{safe}"


def _as_str(value: Any, field_name: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ProfileValidationError(f"Field {field_name!r} must be a non-empty string.")


def _as_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ProfileValidationError(f"Field {field_name!r} must be a boolean.")


def _as_int(value: Any, field_name: str, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProfileValidationError(f"Field {field_name!r} must be an integer.")
    if value < minimum:
        raise ProfileValidationError(f"Field {field_name!r} must be >= {minimum}.")
    return value


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


def _parse_budgets_for_agent(blob: Any, *, defaults: BudgetLimits) -> BudgetLimits:
    if blob is None:
        return defaults
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
        if isinstance(blob["wall_clock_seconds"], bool) or not isinstance(
            blob["wall_clock_seconds"], int | float
        ):
            raise ProfileValidationError("budgets.wall_clock_seconds must be a number.")
        if float(blob["wall_clock_seconds"]) <= 0:
            raise ProfileValidationError("budgets.wall_clock_seconds must be positive.")
        kwargs["wall_clock_seconds"] = float(blob["wall_clock_seconds"])
    if "per_tool_seconds" in blob:
        if isinstance(blob["per_tool_seconds"], bool) or not isinstance(
            blob["per_tool_seconds"], int | float
        ):
            raise ProfileValidationError("budgets.per_tool_seconds must be a number.")
        if float(blob["per_tool_seconds"]) <= 0:
            raise ProfileValidationError("budgets.per_tool_seconds must be positive.")
        kwargs["per_tool_seconds"] = float(blob["per_tool_seconds"])
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
    return BudgetLimits(
        max_steps=int(kwargs.get("max_steps", defaults.max_steps)),
        max_tool_calls=int(kwargs.get("max_tool_calls", defaults.max_tool_calls)),
        wall_clock_seconds=float(kwargs.get("wall_clock_seconds", defaults.wall_clock_seconds)),
        per_tool_seconds=float(kwargs.get("per_tool_seconds", defaults.per_tool_seconds)),
        max_model_tokens=kwargs.get("max_model_tokens", defaults.max_model_tokens),
    )


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


@dataclass(frozen=True)
class WorkspaceSection:
    name: str
    orchestrator: str
    description: str = ""
    trace_dir: Path = Path(".naqsha/traces")
    auto_approve: bool = False
    approval_required_tiers: frozenset[RiskTier] = frozenset(
        {RiskTier.WRITE, RiskTier.HIGH}
    )
    sanitizer_max_chars: int = 4000

    def resolve_trace_dir(self, base_dir: Path) -> Path:
        p = self.trace_dir
        if not p.is_absolute():
            p = (base_dir / p).resolve()
        else:
            p = p.resolve()
        return p


@dataclass(frozen=True)
class ReflectionSection:
    enabled: bool = False
    auto_merge: bool = False
    reliability_gate: bool = True


@dataclass(frozen=True)
class AgentRoleConfig:
    agent_id: str
    role: str
    model_adapter: str
    tools: frozenset[str]
    budgets: BudgetLimits
    max_retries: int = 3
    approval_required_tiers: frozenset[RiskTier] | None = None
    fake_model_messages: tuple[dict[str, Any], ...] | None = None
    instructions: str = ""
    openai_compat: dict[str, Any] | None = None
    anthropic: dict[str, Any] | None = None
    gemini: dict[str, Any] | None = None
    ollama: dict[str, Any] | None = None


@dataclass(frozen=True)
class TeamTopology:
    workspace: WorkspaceSection
    agents: dict[str, AgentRoleConfig]
    memory: TeamMemoryConfig
    reflection: ReflectionSection

    @property
    def orchestrator_id(self) -> str:
        return self.workspace.orchestrator

    def delegate_tool_name_for_worker(self, worker_id: str) -> str:
        return _safe_delegate_tool_name(worker_id)

    def worker_agents(self) -> dict[str, AgentRoleConfig]:
        return {
            aid: cfg
            for aid, cfg in self.agents.items()
            if aid != self.orchestrator_id
        }


def parse_team_topology_file(path: Path) -> TeamTopology:
    raw = path.read_bytes()
    data = tomllib.loads(raw.decode("utf-8"))
    return parse_team_topology(data, base_dir=path.parent.resolve())


def parse_team_topology(data: Mapping[str, Any], *, base_dir: Path) -> TeamTopology:
    """Validate a mapping (typically loaded from ``naqsha.toml``) into a ``TeamTopology``."""

    _ = base_dir  # reserved for relative-path resolution alongside caller workspace root

    allowed_top = {"workspace", "memory", "reflection", "agents"}
    extra = set(data) - allowed_top
    if extra:
        raise ProfileValidationError(f"Unknown top-level keys: {sorted(extra)}.")

    ws = data.get("workspace")
    if not isinstance(ws, Mapping):
        raise ProfileValidationError("'workspace' section is required.")

    name = _as_str(ws.get("name", "team"), "workspace.name")
    orchestrator = _as_str(ws.get("orchestrator"), "workspace.orchestrator")
    dval = ws.get("description", "")
    if dval is None or dval == "":
        description = ""
    elif isinstance(dval, str):
        description = dval.strip()
    else:
        raise ProfileValidationError("'workspace.description' must be a string.")
    trace_dir_raw = ws.get("trace_dir", ".naqsha/traces")
    trace_dir = Path(_as_str(trace_dir_raw, "workspace.trace_dir"))
    auto_approve = _as_bool(ws.get("auto_approve", False), "workspace.auto_approve")
    approval_required_tiers = _parse_risk_tiers(ws.get("approval_required_tiers"))
    sanitizer_max_chars = _as_int(
        ws.get("sanitizer_max_chars", 4000), "workspace.sanitizer_max_chars", minimum=1
    )

    ws_extra = set(ws) - {
        "name",
        "orchestrator",
        "description",
        "trace_dir",
        "auto_approve",
        "approval_required_tiers",
        "sanitizer_max_chars",
    }
    if ws_extra:
        raise ProfileValidationError(f"Unknown workspace keys: {sorted(ws_extra)}.")

    mem_blob = data.get("memory") or {}
    if not isinstance(mem_blob, Mapping):
        raise ProfileValidationError("'memory' must be a table.")
    mem_type = _as_str(mem_blob.get("type", "sqlite"), "memory.type").lower()
    db_path = Path(_as_str(mem_blob.get("db_path", ".naqsha/memory.db"), "memory.db_path"))
    embeddings = _as_bool(mem_blob.get("embeddings", False), "memory.embeddings")
    mem_extra = set(mem_blob) - {"type", "db_path", "embeddings"}
    if mem_extra:
        raise ProfileValidationError(f"Unknown memory keys: {sorted(mem_extra)}.")
    memory = TeamMemoryConfig(type=mem_type, db_path=db_path, embeddings=embeddings)

    refl_blob = data.get("reflection") or {}
    if not isinstance(refl_blob, Mapping):
        raise ProfileValidationError("'reflection' must be a table.")
    reflection = ReflectionSection(
        enabled=_as_bool(refl_blob.get("enabled", False), "reflection.enabled"),
        auto_merge=_as_bool(refl_blob.get("auto_merge", False), "reflection.auto_merge"),
        reliability_gate=_as_bool(
            refl_blob.get("reliability_gate", True), "reflection.reliability_gate"
        ),
    )
    refl_extra = set(refl_blob) - {"enabled", "auto_merge", "reliability_gate"}
    if refl_extra:
        raise ProfileValidationError(f"Unknown reflection keys: {sorted(refl_extra)}.")

    agents_blob = data.get("agents")
    if not isinstance(agents_blob, Mapping) or not agents_blob:
        raise ProfileValidationError("'agents' must be a non-empty table.")

    if orchestrator not in agents_blob:
        raise ProfileValidationError(
            f"workspace.orchestrator {orchestrator!r} is missing from [agents]."
        )

    starter = starter_tool_names()
    agent_keys = [_as_str(str(k), "agents") for k in agents_blob]
    delegates_for_team = frozenset(
        _safe_delegate_tool_name(wid) for wid in agent_keys if wid != orchestrator
    )

    agents: dict[str, AgentRoleConfig] = {}

    for aid_raw, acfg in agents_blob.items():
        agent_id = _as_str(str(aid_raw), "agents.<name>")
        if not isinstance(acfg, Mapping):
            raise ProfileValidationError(f"agents.{agent_id} must be a table.")
        role = _as_str(acfg.get("role", "agent"), f"agents.{agent_id}.role")
        model_adapter = (
            _as_str(acfg.get("model_adapter", "fake"), f"agents.{agent_id}.model_adapter")
            .strip()
            .lower()
            .replace("-", "_")
        )
        if model_adapter not in {"fake", "openai_compat", "anthropic", "gemini", "ollama"}:
            raise ProfileValidationError(
                f"agents.{agent_id}.model_adapter must be one of "
                f"fake, openai_compat, anthropic, gemini, ollama; got {model_adapter!r}."
            )

        openai_blob = acfg.get("openai_compat")
        anthropic_blob = acfg.get("anthropic")
        gemini_blob = acfg.get("gemini")
        ollama_blob = acfg.get("ollama")
        if openai_blob is not None and model_adapter != "openai_compat":
            raise ProfileValidationError(
                f"agents.{agent_id}.openai_compat is only valid when "
                f"model_adapter is openai_compat."
            )
        if anthropic_blob is not None and model_adapter != "anthropic":
            raise ProfileValidationError(
                f"agents.{agent_id}.anthropic is only valid when model_adapter is anthropic."
            )
        if gemini_blob is not None and model_adapter != "gemini":
            raise ProfileValidationError(
                f"agents.{agent_id}.gemini is only valid when model_adapter is gemini."
            )
        if ollama_blob is not None and model_adapter != "ollama":
            raise ProfileValidationError(
                f"agents.{agent_id}.ollama is only valid when model_adapter is ollama."
            )
        if openai_blob is not None and not isinstance(openai_blob, Mapping):
            raise ProfileValidationError(f"agents.{agent_id}.openai_compat must be a table.")
        if anthropic_blob is not None and not isinstance(anthropic_blob, Mapping):
            raise ProfileValidationError(f"agents.{agent_id}.anthropic must be a table.")
        if gemini_blob is not None and not isinstance(gemini_blob, Mapping):
            raise ProfileValidationError(f"agents.{agent_id}.gemini must be a table.")
        if ollama_blob is not None and not isinstance(ollama_blob, Mapping):
            raise ProfileValidationError(f"agents.{agent_id}.ollama must be a table.")

        tools_raw = acfg.get("tools")
        if not isinstance(tools_raw, list) or not tools_raw:
            raise ProfileValidationError(f"agents.{agent_id}.tools must be a non-empty array.")
        tool_set: set[str] = set()
        for t in tools_raw:
            tname = _as_str(t, f"agents.{agent_id}.tools[]")
            tool_set.add(tname)
        if agent_id != orchestrator:
            illegal_del = {t for t in tool_set if t.startswith("delegate_to_")}
            if illegal_del:
                raise ProfileValidationError(
                    f"agents.{agent_id} cannot declare delegation tools: {sorted(illegal_del)}."
                )
        elif delegates_for_team:
            tool_set |= set(delegates_for_team)

        diff = frozenset(tool_set) - starter - MEMORY_DECORATED_TOOL_NAMES
        unknown_tools = diff - delegates_for_team
        if unknown_tools:
            raise ProfileValidationError(
                f"agents.{agent_id}.tools contains unknown names: {sorted(unknown_tools)}."
            )

        default_b = BudgetLimits()
        max_steps = _as_int(
            acfg.get("max_steps", default_b.max_steps), f"agents.{agent_id}.max_steps"
        )
        max_tokens = acfg.get("max_model_tokens")
        if max_tokens is None:
            mt: int | None = default_b.max_model_tokens
        elif isinstance(max_tokens, bool) or not isinstance(max_tokens, int):
            raise ProfileValidationError(f"agents.{agent_id}.max_model_tokens must be int or null.")
        elif max_tokens < 1:
            raise ProfileValidationError(f"agents.{agent_id}.max_model_tokens must be >= 1.")
        else:
            mt = max_tokens

        budgets = BudgetLimits(
            max_steps=max_steps,
            max_tool_calls=default_b.max_tool_calls,
            wall_clock_seconds=default_b.wall_clock_seconds,
            per_tool_seconds=default_b.per_tool_seconds,
            max_model_tokens=mt,
        )
        budgets = _parse_budgets_for_agent(acfg.get("budgets"), defaults=budgets)

        max_retries = _as_int(
            acfg.get("max_retries", 3), f"agents.{agent_id}.max_retries", minimum=0
        )

        ins_raw = acfg.get("instructions", "")
        if ins_raw is None or ins_raw == "":
            agent_instructions_txt = ""
        elif isinstance(ins_raw, str):
            agent_instructions_txt = ins_raw
        else:
            raise ProfileValidationError(f"agents.{agent_id}.instructions must be a string.")

        art = acfg.get("approval_required_tiers")
        tiers: frozenset[RiskTier] | None
        if art is None:
            tiers = None
        else:
            tiers = _parse_risk_tiers(art)

        fake_messages: tuple[dict[str, Any], ...] | None = None
        fm = acfg.get("fake_model")
        json_messages = acfg.get("fake_model_json")
        if fm is not None and json_messages is not None:
            raise ProfileValidationError(
                f"agents.{agent_id}: use only one of fake_model or fake_model_json."
            )
        if fm is not None:
            if not isinstance(fm, Mapping):
                raise ProfileValidationError(f"agents.{agent_id}.fake_model must be a table.")
            if model_adapter != "fake":
                raise ProfileValidationError(
                    f"agents.{agent_id}.fake_model is only valid when model_adapter is fake."
                )
            fm_extra = set(fm) - {"messages"}
            if fm_extra:
                raise ProfileValidationError(
                    f"Unknown agents.{agent_id}.fake_model keys: {sorted(fm_extra)}."
                )
            fake_messages = _validate_fake_messages(fm.get("messages"))
        elif json_messages is not None:
            if model_adapter != "fake":
                raise ProfileValidationError(
                    f"agents.{agent_id}.fake_model_json is only valid when model_adapter is fake."
                )
            if not isinstance(json_messages, str):
                raise ProfileValidationError(
                    f"agents.{agent_id}.fake_model_json must be a string of JSON."
                )
            parsed = json.loads(json_messages)
            if not isinstance(parsed, list):
                raise ProfileValidationError("fake_model_json must decode to a JSON array.")
            fake_messages = _validate_fake_messages(parsed)

        acfg_extra = set(acfg) - {
            "role",
            "model_adapter",
            "tools",
            "max_steps",
            "max_model_tokens",
            "max_retries",
            "budgets",
            "approval_required_tiers",
            "fake_model",
            "fake_model_json",
            "instructions",
            "openai_compat",
            "anthropic",
            "gemini",
            "ollama",
        }
        if acfg_extra:
            raise ProfileValidationError(
                f"Unknown keys for agents.{agent_id}: {sorted(acfg_extra)}."
            )

        agents[agent_id] = AgentRoleConfig(
            agent_id=agent_id,
            role=role,
            model_adapter=model_adapter,
            tools=frozenset(tool_set),
            budgets=budgets,
            max_retries=max_retries,
            approval_required_tiers=tiers,
            fake_model_messages=fake_messages,
            instructions=agent_instructions_txt,
            openai_compat=dict(openai_blob) if openai_blob is not None else None,
            anthropic=dict(anthropic_blob) if anthropic_blob is not None else None,
            gemini=dict(gemini_blob) if gemini_blob is not None else None,
            ollama=dict(ollama_blob) if ollama_blob is not None else None,
        )

    return TeamTopology(
        workspace=WorkspaceSection(
            name=name,
            orchestrator=orchestrator,
            description=description,
            trace_dir=trace_dir,
            auto_approve=auto_approve,
            approval_required_tiers=approval_required_tiers,
            sanitizer_max_chars=sanitizer_max_chars,
        ),
        agents=agents,
        memory=memory,
        reflection=reflection,
    )

"""Tool-Based Delegation and team trace integration tests."""

from __future__ import annotations

from pathlib import Path

from naqsha.core.approvals import StaticApprovalGate
from naqsha.core.event_bus import RuntimeEventBus
from naqsha.core.events import CircuitBreakerTripped
from naqsha.memory.sharing import TeamMemoryConfig, open_team_memory_engine
from naqsha.orchestration.team_runtime import build_team_orchestrator_runtime
from naqsha.orchestration.topology import parse_team_topology
from naqsha.tracing.jsonl import JsonlTraceStore


def _two_agent_dict(
    *,
    orch_msgs: list[dict],
    worker_msgs: list[dict],
    orch_tools: list[str] | None = None,
    worker_tools: list[str] | None = None,
) -> dict:
    return {
        "workspace": {
            "name": "tw",
            "orchestrator": "orch",
            "auto_approve": True,
        },
        "memory": {"db_path": ".naqsha/memory.db"},
        "reflection": {},
        "agents": {
            "orch": {
                "role": "orchestrator",
                "model_adapter": "fake",
                "tools": orch_tools or ["clock"],
                "fake_model": {"messages": orch_msgs},
            },
            "worker": {
                "role": "worker",
                "model_adapter": "fake",
                "tools": worker_tools or ["clock", "list_memory_tables"],
                "fake_model": {"messages": worker_msgs},
            },
        },
    }


def test_implicit_tool_approval_wires_open_gate(tmp_path: Path) -> None:
    orch_msgs = [{"kind": "answer", "text": "ok"}]
    worker_msgs = [{"kind": "answer", "text": "w"}]
    body = _two_agent_dict(
        orch_msgs=orch_msgs,
        worker_msgs=worker_msgs,
        orch_tools=["clock"],
        worker_tools=["clock", "list_memory_tables"],
    )
    body["workspace"]["auto_approve"] = False
    topo = parse_team_topology(body, base_dir=tmp_path)
    rt = build_team_orchestrator_runtime(topo, tmp_path, implicit_tool_approval=True)
    gate = rt.config.approval_gate
    assert isinstance(gate, StaticApprovalGate)
    assert gate.approved is True


def test_two_agent_delegation_hierarchical_trace(tmp_path: Path) -> None:
    orch_msgs = [
        {
            "kind": "action",
            "calls": [
                {
                    "id": "d1",
                    "name": "delegate_to_worker",
                    "arguments": {"task": "hello"},
                },
            ],
        },
        {"kind": "answer", "text": "orch done"},
    ]
    worker_msgs = [
        {
            "kind": "action",
            "calls": [{"id": "c1", "name": "clock", "arguments": {}}],
        },
        {"kind": "answer", "text": "worker was here"},
    ]
    topo = parse_team_topology(
        _two_agent_dict(orch_msgs=orch_msgs, worker_msgs=worker_msgs),
        base_dir=tmp_path,
    )
    bus = RuntimeEventBus()
    rt = build_team_orchestrator_runtime(topo, tmp_path, event_bus=bus)
    res = rt.run("start")
    assert res.answer == "orch done"
    assert not res.failed

    store = JsonlTraceStore(topo.workspace.resolve_trace_dir(tmp_path))
    loaded = store.load(res.run_id)
    agents_in_trace = {e.agent_id for e in loaded if e.schema_version >= 2}
    assert "orch" in agents_in_trace
    assert "worker" in agents_in_trace

    worker_queries = [e for e in loaded if e.kind == "query" and e.agent_id == "worker"]
    assert len(worker_queries) >= 1
    assert worker_queries[0].parent_span_id is not None


def test_shared_memory_table_visible_to_worker(tmp_path: Path) -> None:
    engine = open_team_memory_engine(tmp_path, TeamMemoryConfig(db_path=Path(".naqsha/memory.db")))
    scope = engine.get_shared_scope()
    scope.execute("CREATE TABLE seed (note TEXT)")
    scope.execute("INSERT INTO seed (note) VALUES ('team-note')")
    engine.close()

    orch_msgs = [
        {
            "kind": "action",
            "calls": [
                {
                    "id": "d1",
                    "name": "delegate_to_worker",
                    "arguments": {"task": "list tables"},
                },
            ],
        },
        {"kind": "answer", "text": "ok"},
    ]
    worker_msgs = [
        {
            "kind": "action",
            "calls": [{"id": "l1", "name": "list_memory_tables", "arguments": {}}],
        },
        {"kind": "answer", "text": "listed"},
    ]
    topo = parse_team_topology(
        _two_agent_dict(orch_msgs=orch_msgs, worker_msgs=worker_msgs),
        base_dir=tmp_path,
    )
    rt = build_team_orchestrator_runtime(topo, tmp_path)
    res = rt.run("go")
    assert not res.failed
    store = JsonlTraceStore(topo.workspace.resolve_trace_dir(tmp_path))
    loaded = store.load(res.run_id)
    worker_obs = [
        e
        for e in loaded
        if e.kind == "observation"
        and e.agent_id == "worker"
        and e.payload.get("tool") == "list_memory_tables"
    ]
    assert worker_obs
    text = worker_obs[0].payload["observation"]["content"]
    assert "seed" in text.lower()


def test_worker_circuit_breaker_escalates_task_failed_error_to_orchestrator(
    tmp_path: Path,
) -> None:
    """Orchestrator receives ``TaskFailedError`` metadata when a worker breaker trips."""

    orch_msgs = [
        {
            "kind": "action",
            "calls": [
                {
                    "id": "d1",
                    "name": "delegate_to_worker",
                    "arguments": {"task": "break me"},
                },
            ],
        },
        {"kind": "answer", "text": "orch continued"},
    ]
    worker_msgs = [
        {
            "kind": "action",
            "calls": [
                {
                    "id": "c1",
                    "name": "calculator",
                    "arguments": {"expression": "1/0"},
                },
            ],
        },
    ]
    data = _two_agent_dict(
        orch_msgs=orch_msgs,
        worker_msgs=worker_msgs,
        orch_tools=["clock"],
        worker_tools=["calculator"],
    )
    data["agents"]["worker"]["max_retries"] = 1

    topo = parse_team_topology(data, base_dir=tmp_path)
    bus = RuntimeEventBus()
    tripped: list[CircuitBreakerTripped] = []
    bus.subscribe(
        lambda e: tripped.append(e) if isinstance(e, CircuitBreakerTripped) else None
    )

    rt = build_team_orchestrator_runtime(topo, tmp_path, event_bus=bus)
    result = rt.run("go")
    assert not result.failed
    assert result.answer == "orch continued"

    worker_breaks = [e for e in tripped if e.agent_id == "worker"]
    assert worker_breaks, "worker should emit CircuitBreakerTripped on first tool failure"

    store = JsonlTraceStore(topo.workspace.resolve_trace_dir(tmp_path))
    loaded = store.load(result.run_id)
    orch_delegate_obs = [
        e
        for e in loaded
        if e.kind == "observation"
        and e.agent_id == "orch"
        and e.payload.get("tool") == "delegate_to_worker"
    ]
    assert orch_delegate_obs
    meta = orch_delegate_obs[0].payload["observation"].get("metadata") or {}
    assert meta.get("kind") == "TaskFailedError"
    assert meta.get("failure_code") == "circuit_breaker_tripped"
    assert meta.get("circuit_breaker") is True

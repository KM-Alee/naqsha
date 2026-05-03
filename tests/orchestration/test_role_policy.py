"""Role-Based Tool Policy enforcement for worker agents."""

from __future__ import annotations

from pathlib import Path

from naqsha.core.event_bus import RuntimeEventBus
from naqsha.core.events import ToolErrored
from naqsha.orchestration.team_runtime import build_team_orchestrator_runtime
from naqsha.orchestration.topology import parse_team_topology


def test_worker_policy_denial_emits_tool_errored(tmp_path: Path) -> None:
    orch_msgs = [
        {
            "kind": "action",
            "calls": [
                {
                    "id": "d1",
                    "name": "delegate_to_worker",
                    "arguments": {"task": "calculate"},
                },
            ],
        },
        {"kind": "answer", "text": "orch done"},
    ]
    worker_msgs = [
        {
            "kind": "action",
            "calls": [
                {
                    "id": "calc-1",
                    "name": "calculator",
                    "arguments": {"expression": "1+1"},
                },
            ],
        },
        {"kind": "answer", "text": "should not get here"},
    ]
    data = {
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
                "tools": ["clock"],
                "fake_model": {"messages": orch_msgs},
            },
            "worker": {
                "role": "worker",
                "model_adapter": "fake",
                "tools": ["clock"],
                "fake_model": {"messages": worker_msgs},
            },
        },
    }
    topo = parse_team_topology(data, base_dir=tmp_path)
    bus = RuntimeEventBus()
    collected: list[object] = []
    bus.subscribe(collected.append)
    rt = build_team_orchestrator_runtime(topo, tmp_path, event_bus=bus)
    res = rt.run("start")
    assert not res.failed

    errors = [e for e in collected if isinstance(e, ToolErrored)]
    assert errors
    assert any(e.tool_name == "calculator" for e in errors)
    assert any(e.agent_id == "worker" for e in errors)

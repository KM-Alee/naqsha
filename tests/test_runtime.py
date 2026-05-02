import sys

from naqsha.approvals import StaticApprovalGate
from naqsha.memory.inmemory import InMemoryMemoryPort
from naqsha.models.fake import FakeModelClient
from naqsha.policy import ToolPolicy
from naqsha.protocols.nap import NapAction, NapAnswer, ToolCall
from naqsha.runtime import CoreRuntime, RuntimeConfig
from naqsha.sanitizer import ObservationSanitizer
from naqsha.tools.starter import starter_tools
from naqsha.trace.jsonl import JsonlTraceStore


def build_runtime(tmp_path, messages, *, approved: bool = False) -> CoreRuntime:
    tools = starter_tools(tmp_path)
    return CoreRuntime(
        RuntimeConfig(
            model=FakeModelClient(messages),
            tools=tools,
            trace_store=JsonlTraceStore(tmp_path / "traces"),
            policy=ToolPolicy.allow_all_starter_tools(tools),
            approval_gate=StaticApprovalGate(approved=approved),
            sanitizer=ObservationSanitizer(max_chars=80),
        )
    )


def test_runtime_executes_tool_and_persists_qaoa_trace(tmp_path) -> None:
    runtime = build_runtime(
        tmp_path,
        [
            NapAction(
                calls=(
                    ToolCall(
                        id="calc-1",
                        name="calculator",
                        arguments={"expression": "2 + 3 * 4"},
                    ),
                )
            ),
            NapAnswer(text="The result is 14."),
        ],
    )

    result = runtime.run("calculate")

    assert result.answer == "The result is 14."
    assert [event.kind for event in result.events] == ["query", "action", "observation", "answer"]
    assert result.events[2].payload["observation"]["content"] == "14.0"


def test_policy_denies_high_risk_tool_without_approval(tmp_path) -> None:
    runtime = build_runtime(
        tmp_path,
        [
            NapAction(
                calls=(
                    ToolCall(
                        id="shell-1",
                        name="run_shell",
                        arguments={"argv": [sys.executable, "-c", "pass"], "cwd": "."},
                    ),
                )
            ),
            NapAnswer(text="done"),
        ],
        approved=False,
    )

    result = runtime.run("try shell")

    observation = result.events[2].payload["observation"]
    assert observation["ok"] is False
    assert observation["metadata"]["policy"] == "denied"
    assert "Approval denied" in observation["content"]


def test_memory_receives_only_sanitized_observations(tmp_path) -> None:
    (tmp_path / "secret.txt").write_text("token=sk-abc123abc123abc123", encoding="utf-8")
    memory = InMemoryMemoryPort()
    tools = starter_tools(tmp_path)
    runtime = CoreRuntime(
        RuntimeConfig(
            model=FakeModelClient(
                [
                    NapAction(
                        calls=(
                            ToolCall(
                                id="read-1",
                                name="read_file",
                                arguments={"path": "secret.txt"},
                            ),
                        )
                    ),
                    NapAnswer(text="done"),
                ]
            ),
            tools=tools,
            trace_store=JsonlTraceStore(tmp_path / "traces"),
            policy=ToolPolicy.allow_all_starter_tools(tools),
            approval_gate=StaticApprovalGate(approved=True),
            memory=memory,
        )
    )

    result = runtime.run("write a secret-looking value")

    assert result.answer == "done"
    assert memory.started_runs == [result.run_id]
    assert memory.finished_runs == [result.run_id]
    assert all("sk-" not in record.content for record in memory.records)

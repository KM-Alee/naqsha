"""Golden scenarios for SimpleMem-Cross-style durable memory (Phase 5)."""

from __future__ import annotations

import time

import pytest

from naqsha.approvals import StaticApprovalGate
from naqsha.memory.simplemem_cross import (
    MEMORY_BEGIN,
    SimpleMemCrossMemoryPort,
)
from naqsha.models.fake import FakeModelClient
from naqsha.policy import ToolPolicy
from naqsha.protocols.nap import NapAction, NapAnswer, ToolCall
from naqsha.runtime import CoreRuntime, RuntimeConfig
from naqsha.sanitizer import ObservationSanitizer
from naqsha.tools.base import ToolObservation
from naqsha.tools.starter import starter_tools
from naqsha.trace.jsonl import JsonlTraceStore


def _runtime(tmp_path, memory: SimpleMemCrossMemoryPort, messages) -> CoreRuntime:
    tools = starter_tools(tmp_path)
    return CoreRuntime(
        RuntimeConfig(
            model=FakeModelClient(messages),
            tools=tools,
            trace_store=JsonlTraceStore(tmp_path / "traces"),
            policy=ToolPolicy.allow_all_starter_tools(tools),
            approval_gate=StaticApprovalGate(approved=True),
            sanitizer=ObservationSanitizer(max_chars=4000),
            memory=memory,
            memory_token_budget=8000,
        )
    )


def test_cross_session_recall(tmp_path) -> None:
    db = tmp_path / "cross.sqlite"
    mem_first = SimpleMemCrossMemoryPort(project="qa", database_path=db)
    try:
        r1 = _runtime(
            tmp_path,
            mem_first,
            [
                NapAction(
                    calls=(
                        ToolCall(
                            id="c1",
                            name="calculator",
                            arguments={"expression": "7 * 8"},
                        ),
                    )
                ),
                NapAnswer(text="Product is fifty-six."),
            ],
        )
        r1.run("math warmup")

        mem_second = SimpleMemCrossMemoryPort(project="qa", database_path=db)
        try:
            r2 = _runtime(
                tmp_path,
                mem_second,
                [NapAnswer(text="Recalled prior context.")],
            )
            r2.run("What was the calculator product from before?")
            mem_reader = SimpleMemCrossMemoryPort(project="qa", database_path=db)
            try:
                recalled = mem_reader.retrieve("calculator product fifty-six", token_budget=500)
                assert recalled
                joined = "\n".join(r.content for r in recalled)
                assert "56" in joined or "fifty-six" in joined.lower()
                assert MEMORY_BEGIN in recalled[0].content
                assert "evidence=" in recalled[0].provenance
            finally:
                mem_reader.close()
        finally:
            mem_second.close()
    finally:
        mem_first.close()


def test_irrelevant_memory_suppressed(tmp_path) -> None:
    db = tmp_path / "cross.sqlite"
    mem = SimpleMemCrossMemoryPort(project="p", database_path=db)
    try:
        mem.start_run("r1", "colors")
        mem.record_observation(
            "r1",
            "echo",
            ToolObservation(ok=True, content="I enjoy hiking in the alps.", metadata={}),
        )
        mem.finish_run("r1", "Noted.")
        rows = mem.retrieve("database schema migrations", token_budget=500)
        assert rows == []
    finally:
        mem.close()


def test_latest_preference_wins_ordering(tmp_path) -> None:
    db = tmp_path / "cross.sqlite"
    mem_a = SimpleMemCrossMemoryPort(project="pricing", database_path=db)
    try:
        mem_a.start_run("legacy", "pricing snapshot")
        mem_a.finish_run("legacy", "plan=starter_rollout inactive_channel")
        time.sleep(0.01)
        mem_b = SimpleMemCrossMemoryPort(project="pricing", database_path=db)
        try:
            mem_b.start_run("current", "pricing update")
            mem_b.finish_run("current", "plan=enterprise_rollout active_channel")
            mem_r = SimpleMemCrossMemoryPort(project="pricing", database_path=db)
            try:
                rows = mem_r.retrieve("rollout plan active channel", token_budget=8000)
                assert rows
                assert "enterprise" in rows[0].content.lower()
            finally:
                mem_r.close()
        finally:
            mem_b.close()
    finally:
        mem_a.close()


def test_provenance_echoes_run_and_evidence(tmp_path) -> None:
    db = tmp_path / "cross.sqlite"
    mem_w = SimpleMemCrossMemoryPort(project="p", database_path=db)
    try:
        r = _runtime(
            tmp_path,
            mem_w,
            [
                NapAction(
                    calls=(
                        ToolCall(
                            id="c1",
                            name="clock",
                            arguments={},
                        ),
                    )
                ),
                NapAnswer(text="done"),
            ],
        )
        out = r.run("check time")
        mem_r = SimpleMemCrossMemoryPort(project="p", database_path=db)
        try:
            rows = mem_r.retrieve("", token_budget=4000)
            rid = out.run_id
            assert rows
            assert any(rid in r.provenance and ":clock" in r.provenance for r in rows)
        finally:
            mem_r.close()
    finally:
        mem_w.close()


def test_record_observation_requires_active_run(tmp_path) -> None:
    mem = SimpleMemCrossMemoryPort(project="p", database_path=tmp_path / "z.sqlite")
    try:
        with pytest.raises(ValueError, match="mismatched run_id"):
            mem.record_observation(
                "nope",
                "clock",
                ToolObservation(ok=True, content="x", metadata={}),
            )
    finally:
        mem.close()

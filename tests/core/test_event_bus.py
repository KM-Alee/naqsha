"""Tests for the Typed Event Bus."""

import pytest

from naqsha.core.event_bus import RuntimeEventBus
from naqsha.core.events import (
    RunCompleted,
    RunStarted,
    ToolCompleted,
    ToolInvoked,
)


def test_event_bus_subscribe_and_emit():
    """Test that subscribers receive emitted events."""
    bus = RuntimeEventBus()
    collected_events = []

    def handler(event):
        collected_events.append(event)

    bus.subscribe(handler)

    event1 = RunStarted(run_id="test-1", agent_id="agent-1", query="test query")
    event2 = ToolInvoked(
        run_id="test-1",
        agent_id="agent-1",
        tool_name="test_tool",
        call_id="call-1",
        arguments={"arg": "value"},
    )
    event3 = RunCompleted(
        run_id="test-1",
        agent_id="agent-1",
        answer="test answer",
        total_steps=5,
    )

    bus.emit(event1)
    bus.emit(event2)
    bus.emit(event3)

    assert len(collected_events) == 3
    assert collected_events[0] == event1
    assert collected_events[1] == event2
    assert collected_events[2] == event3


def test_event_bus_multiple_subscribers():
    """Test that multiple subscribers all receive events."""
    bus = RuntimeEventBus()
    collected_1 = []
    collected_2 = []

    bus.subscribe(lambda e: collected_1.append(e))
    bus.subscribe(lambda e: collected_2.append(e))

    event = RunStarted(run_id="test-1", agent_id="agent-1", query="test")
    bus.emit(event)

    assert len(collected_1) == 1
    assert len(collected_2) == 1
    assert collected_1[0] == event
    assert collected_2[0] == event


def test_event_bus_subscriber_exception_does_not_break_bus():
    """Test that a failing subscriber doesn't break the event bus."""
    bus = RuntimeEventBus()
    collected = []

    def failing_handler(event):
        raise ValueError("Subscriber error")

    def working_handler(event):
        collected.append(event)

    bus.subscribe(failing_handler)
    bus.subscribe(working_handler)

    event = RunStarted(run_id="test-1", agent_id="agent-1", query="test")
    bus.emit(event)

    assert len(collected) == 1
    assert collected[0] == event


def test_event_bus_clear_subscribers():
    """Test that clear_subscribers removes all subscribers."""
    bus = RuntimeEventBus()
    collected = []

    bus.subscribe(lambda e: collected.append(e))
    bus.clear_subscribers()

    event = RunStarted(run_id="test-1", agent_id="agent-1", query="test")
    bus.emit(event)

    assert len(collected) == 0


@pytest.mark.asyncio
async def test_event_bus_async_generator():
    """Test the async events() generator."""
    bus = RuntimeEventBus()

    event1 = RunStarted(run_id="test-1", agent_id="agent-1", query="test")
    event2 = ToolCompleted(
        run_id="test-1",
        agent_id="agent-1",
        tool_name="test_tool",
        call_id="call-1",
        observation="result",
    )

    bus.emit(event1)
    bus.emit(event2)

    collected = []
    async for event in bus.events():
        collected.append(event)
        if len(collected) == 2:
            break

    assert len(collected) == 2
    assert collected[0] == event1
    assert collected[1] == event2

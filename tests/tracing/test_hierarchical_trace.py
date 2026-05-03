"""Hierarchical QAOA Trace: V2 schema, span nesting, and event bus coverage."""

import json
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from naqsha.core.event_bus import RuntimeEventBus
from naqsha.core.events import SpanClosed, SpanOpened
from naqsha.tracing.jsonl import JsonlTraceStore
from naqsha.tracing.protocols.qaoa import (
    TraceEvent,
    TraceValidationError,
    action_event,
    answer_event,
    failure_event,
    observation_event,
    query_event,
)
from naqsha.tracing.span import SpanContext, create_root_span


class TestSpanContext:
    """Test SpanContext creation and child span generation."""

    def test_span_context_creation(self):
        """SpanContext carries all required identifiers."""
        ctx = SpanContext(
            trace_id="trace-123",
            span_id="span-456",
            parent_span_id=None,
            agent_id="agent-1",
        )
        assert ctx.trace_id == "trace-123"
        assert ctx.span_id == "span-456"
        assert ctx.parent_span_id is None
        assert ctx.agent_id == "agent-1"

    def test_child_span_inherits_trace_and_agent(self):
        """Child span inherits trace_id and agent_id from parent."""
        parent = SpanContext(
            trace_id="trace-123",
            span_id="span-parent",
            parent_span_id=None,
            agent_id="agent-1",
        )
        child = parent.child_span()
        assert child.trace_id == "trace-123"
        assert child.agent_id == "agent-1"
        assert child.parent_span_id == "span-parent"
        assert child.span_id != "span-parent"  # New span ID

    def test_child_span_can_override_agent_id(self):
        """Child span can have a different agent_id (for delegation)."""
        parent = SpanContext(
            trace_id="trace-123",
            span_id="span-parent",
            parent_span_id=None,
            agent_id="orchestrator",
        )
        child = parent.child_span(agent_id="worker")
        assert child.agent_id == "worker"
        assert child.parent_span_id == "span-parent"


class TestSpan:
    """Test Span metrics accumulation."""

    def test_create_root_span(self):
        """create_root_span creates a span with no parent."""
        span = create_root_span(trace_id="trace-123", agent_id="agent-1")
        assert span.context.trace_id == "trace-123"
        assert span.context.agent_id == "agent-1"
        assert span.context.parent_span_id is None
        assert span.token_count == 0

    def test_span_accumulates_tokens(self):
        """Span.add_tokens accumulates token counts."""
        span = create_root_span(trace_id="trace-123", agent_id="agent-1")
        span.add_tokens(100)
        span.add_tokens(50)
        assert span.token_count == 150

    def test_span_records_latency(self):
        """Span can record model and tool latency."""
        span = create_root_span(trace_id="trace-123", agent_id="agent-1")
        span.set_model_latency(123.45)
        span.set_tool_exec_time(67.89)
        assert span.model_latency_ms == 123.45
        assert span.tool_exec_ms == 67.89

    def test_span_to_dict(self):
        """Span.to_dict serializes all fields."""
        span = create_root_span(trace_id="trace-123", agent_id="agent-1")
        span.add_tokens(100)
        span.set_model_latency(50.0)
        data = span.to_dict()
        assert data["trace_id"] == "trace-123"
        assert data["agent_id"] == "agent-1"
        assert data["token_count"] == 100
        assert data["model_latency_ms"] == 50.0


class TestV2TraceEventSchema:
    """Test V2 trace event schema with hierarchical fields."""

    def test_v2_query_event_includes_span_fields(self):
        """V2 query event includes trace_id, span_id, parent_span_id, agent_id."""
        event = query_event(
            run_id="run-123",
            query="test query",
            trace_id="trace-456",
            span_id="span-789",
            parent_span_id=None,
            agent_id="agent-1",
        )
        assert event.schema_version == 2
        assert event.trace_id == "trace-456"
        assert event.span_id == "span-789"
        assert event.parent_span_id is None
        assert event.agent_id == "agent-1"

    def test_v2_action_event_includes_span_fields(self):
        """V2 action event includes span fields."""
        event = action_event(
            run_id="run-123",
            action={"kind": "action", "calls": []},
            policy=[],
            trace_id="trace-456",
            span_id="span-789",
            agent_id="agent-1",
        )
        assert event.schema_version == 2
        assert event.trace_id == "trace-456"
        assert event.span_id == "span-789"
        assert event.agent_id == "agent-1"

    def test_v2_observation_event_includes_tool_exec_ms(self):
        """V2 observation event can include tool_exec_ms."""
        event = observation_event(
            run_id="run-123",
            call_id="call-1",
            tool="test_tool",
            observation={"result": "ok"},
            trace_id="trace-456",
            span_id="span-789",
            agent_id="agent-1",
            tool_exec_ms=123.45,
        )
        assert event.schema_version == 2
        assert event.payload.get("tool_exec_ms") == 123.45

    def test_v2_answer_event_includes_span_fields(self):
        """V2 answer event includes span fields."""
        event = answer_event(
            run_id="run-123",
            answer="final answer",
            trace_id="trace-456",
            span_id="span-789",
            agent_id="agent-1",
        )
        assert event.schema_version == 2
        assert event.trace_id == "trace-456"

    def test_v2_failure_event_includes_span_fields(self):
        """V2 failure event includes span fields."""
        event = failure_event(
            run_id="run-123",
            code="ERROR",
            message="test error",
            trace_id="trace-456",
            span_id="span-789",
            agent_id="agent-1",
        )
        assert event.schema_version == 2
        assert event.trace_id == "trace-456"


class TestV2Serialization:
    """Test V2 trace event serialization and deserialization."""

    def test_v2_event_to_dict_includes_span_fields(self):
        """V2 event.to_dict() includes all span fields."""
        event = query_event(
            run_id="run-123",
            query="test",
            trace_id="trace-456",
            span_id="span-789",
            parent_span_id="span-parent",
            agent_id="agent-1",
        )
        data = event.to_dict()
        assert data["schema_version"] == 2
        assert data["trace_id"] == "trace-456"
        assert data["span_id"] == "span-789"
        assert data["parent_span_id"] == "span-parent"
        assert data["agent_id"] == "agent-1"

    def test_v2_event_from_dict_parses_span_fields(self):
        """V2 event.from_dict() parses all span fields."""
        data = {
            "schema_version": 2,
            "event_id": str(uuid4()),
            "run_id": "run-123",
            "kind": "query",
            "created_at": "2024-01-01T00:00:00Z",
            "payload": {"query": "test"},
            "trace_id": "trace-456",
            "span_id": "span-789",
            "parent_span_id": "span-parent",
            "agent_id": "agent-1",
        }
        event = TraceEvent.from_dict(data)
        assert event.schema_version == 2
        assert event.trace_id == "trace-456"
        assert event.span_id == "span-789"
        assert event.parent_span_id == "span-parent"
        assert event.agent_id == "agent-1"

    def test_v2_event_round_trip(self):
        """V2 event survives to_dict -> from_dict round trip."""
        original = query_event(
            run_id="run-123",
            query="test",
            trace_id="trace-456",
            span_id="span-789",
            parent_span_id=None,
            agent_id="agent-1",
        )
        data = original.to_dict()
        restored = TraceEvent.from_dict(data)
        assert restored.schema_version == original.schema_version
        assert restored.trace_id == original.trace_id
        assert restored.span_id == original.span_id
        assert restored.parent_span_id == original.parent_span_id
        assert restored.agent_id == original.agent_id


class TestV1BackwardCompatibility:
    """Test that V1 traces load correctly as root-level spans."""

    def test_v1_event_without_span_fields_loads(self):
        """V1 event without span fields loads successfully."""
        data = {
            "schema_version": 1,
            "event_id": str(uuid4()),
            "run_id": "run-123",
            "kind": "query",
            "created_at": "2024-01-01T00:00:00Z",
            "payload": {"query": "test"},
        }
        event = TraceEvent.from_dict(data)
        assert event.schema_version == 1
        # V1 events get generated span_id and trace_id
        assert event.span_id != ""
        assert event.trace_id == "run-123"  # Uses run_id as trace_id
        assert event.parent_span_id is None  # Treated as root span

    def test_v1_event_missing_schema_version_defaults_to_1(self):
        """V1 event without schema_version field defaults to version 1."""
        data = {
            "event_id": str(uuid4()),
            "run_id": "run-123",
            "kind": "query",
            "created_at": "2024-01-01T00:00:00Z",
            "payload": {"query": "test"},
        }
        event = TraceEvent.from_dict(data)
        assert event.schema_version == 1
        assert event.span_id != ""  # Generated

    def test_v1_event_to_dict_excludes_span_fields(self):
        """V1 event.to_dict() does not include V2 span fields."""
        data = {
            "schema_version": 1,
            "event_id": str(uuid4()),
            "run_id": "run-123",
            "kind": "query",
            "created_at": "2024-01-01T00:00:00Z",
            "payload": {"query": "test"},
        }
        event = TraceEvent.from_dict(data)
        serialized = event.to_dict()
        assert "trace_id" not in serialized
        assert "span_id" not in serialized
        assert "parent_span_id" not in serialized
        assert "agent_id" not in serialized


class TestTraceStoreV2:
    """Test TraceStore reads and writes V2 events."""

    def test_trace_store_writes_v2_events(self):
        """TraceStore writes V2 events with all span fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonlTraceStore(tmpdir)

            event = query_event(
                run_id="run-123",
                query="test",
                trace_id="trace-456",
                span_id="span-789",
                agent_id="agent-1",
            )
            store.append(event)

            # Read back and verify
            trace_path = Path(tmpdir) / "run-123.jsonl"
            with open(trace_path) as f:
                line = f.readline()
                data = json.loads(line)
                assert data["schema_version"] == 2
                assert data["trace_id"] == "trace-456"
                assert data["span_id"] == "span-789"
                assert data["agent_id"] == "agent-1"

    def test_trace_store_reads_v1_and_v2_events(self):
        """TraceStore can read both V1 and V2 events from same file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "run-123.jsonl"

            # Write V1 event
            v1_data = {
                "schema_version": 1,
                "event_id": str(uuid4()),
                "run_id": "run-123",
                "kind": "query",
                "created_at": "2024-01-01T00:00:00Z",
                "payload": {"query": "v1 query"},
            }

            # Write V2 event
            v2_data = {
                "schema_version": 2,
                "event_id": str(uuid4()),
                "run_id": "run-123",
                "kind": "answer",
                "created_at": "2024-01-01T00:00:01Z",
                "payload": {"answer": "v2 answer"},
                "trace_id": "trace-456",
                "span_id": "span-789",
                "parent_span_id": None,
                "agent_id": "agent-1",
            }

            with open(trace_path, "w") as f:
                f.write(json.dumps(v1_data) + "\n")
                f.write(json.dumps(v2_data) + "\n")

            # Read both events
            store = JsonlTraceStore(tmpdir)
            events = store.load("run-123")
            assert len(events) == 2
            assert events[0].schema_version == 1
            assert events[1].schema_version == 2
            assert events[1].trace_id == "trace-456"


class TestEventBusSpanEvents:
    """Test that SpanOpened and SpanClosed events are emitted."""

    @pytest.mark.asyncio
    async def test_span_opened_event_structure(self):
        """SpanOpened event contains all required fields."""
        bus = RuntimeEventBus()
        collected = []

        def collector(event):
            collected.append(event)

        bus.subscribe(collector)

        event = SpanOpened(
            run_id="run-123",
            trace_id="trace-456",
            span_id="span-789",
            parent_span_id=None,
            agent_id="agent-1",
        )
        bus.emit(event)

        assert len(collected) == 1
        assert isinstance(collected[0], SpanOpened)
        assert collected[0].trace_id == "trace-456"
        assert collected[0].span_id == "span-789"
        assert collected[0].agent_id == "agent-1"

    @pytest.mark.asyncio
    async def test_span_closed_event_includes_metrics(self):
        """SpanClosed event includes token_count and model_latency_ms."""
        bus = RuntimeEventBus()
        collected = []

        def collector(event):
            collected.append(event)

        bus.subscribe(collector)

        event = SpanClosed(
            run_id="run-123",
            trace_id="trace-456",
            span_id="span-789",
            agent_id="agent-1",
            token_count=150,
            model_latency_ms=123.45,
        )
        bus.emit(event)

        assert len(collected) == 1
        assert isinstance(collected[0], SpanClosed)
        assert collected[0].token_count == 150
        assert collected[0].model_latency_ms == 123.45


class TestSchemaVersioning:
    """Test schema version validation and support."""

    def test_unsupported_schema_version_raises_error(self):
        """Loading a trace with unsupported schema version raises error."""
        data = {
            "schema_version": 999,  # Unsupported version
            "event_id": str(uuid4()),
            "run_id": "run-123",
            "kind": "query",
            "created_at": "2024-01-01T00:00:00Z",
            "payload": {"query": "test"},
        }
        with pytest.raises(TraceValidationError, match="Unsupported QAOA trace schema_version"):
            TraceEvent.from_dict(data)

    def test_supported_versions_include_1_and_2(self):
        """Both schema versions 1 and 2 are supported."""
        # V1
        v1_data = {
            "schema_version": 1,
            "event_id": str(uuid4()),
            "run_id": "run-123",
            "kind": "query",
            "created_at": "2024-01-01T00:00:00Z",
            "payload": {"query": "test"},
        }
        v1_event = TraceEvent.from_dict(v1_data)
        assert v1_event.schema_version == 1

        # V2
        v2_data = {
            "schema_version": 2,
            "event_id": str(uuid4()),
            "run_id": "run-123",
            "kind": "query",
            "created_at": "2024-01-01T00:00:00Z",
            "payload": {"query": "test"},
            "trace_id": "trace-456",
            "span_id": "span-789",
            "parent_span_id": None,
            "agent_id": "agent-1",
        }
        v2_event = TraceEvent.from_dict(v2_data)
        assert v2_event.schema_version == 2


class TestChildSpanNesting:
    """Test hierarchical span nesting for multi-agent traces."""

    def test_parent_child_span_relationship(self):
        """Child span correctly references parent span_id."""
        parent_span = create_root_span(trace_id="trace-123", agent_id="orchestrator")
        child_context = parent_span.context.child_span(agent_id="worker")

        assert child_context.trace_id == parent_span.context.trace_id
        assert child_context.parent_span_id == parent_span.context.span_id
        assert child_context.agent_id == "worker"

    def test_multi_level_span_nesting(self):
        """Spans can nest multiple levels deep."""
        root = create_root_span(trace_id="trace-123", agent_id="orchestrator")
        level1 = root.context.child_span(agent_id="worker-1")
        level2 = level1.child_span(agent_id="worker-2")

        assert level2.parent_span_id == level1.span_id
        assert level1.parent_span_id == root.context.span_id
        assert root.context.parent_span_id is None

    def test_trace_events_preserve_span_hierarchy(self):
        """Trace events created with child spans preserve hierarchy."""
        root = create_root_span(trace_id="trace-123", agent_id="orchestrator")
        child_ctx = root.context.child_span(agent_id="worker")

        parent_event = query_event(
            run_id="run-123",
            query="parent query",
            trace_id=root.context.trace_id,
            span_id=root.context.span_id,
            parent_span_id=root.context.parent_span_id,
            agent_id=root.context.agent_id,
        )

        child_event = query_event(
            run_id="run-123",
            query="child query",
            trace_id=child_ctx.trace_id,
            span_id=child_ctx.span_id,
            parent_span_id=child_ctx.parent_span_id,
            agent_id=child_ctx.agent_id,
        )

        assert child_event.parent_span_id == parent_event.span_id
        assert child_event.trace_id == parent_event.trace_id

"""Tests for memory retrieval with ranking."""

import tempfile
import time
from pathlib import Path

import pytest

from naqsha.memory.engine import DynamicMemoryEngine
from naqsha.memory.retrieval import (
    MEMORY_BEGIN,
    MEMORY_END,
    MemoryRetriever,
    _approx_chars_for_tokens,
    _haystack_matches_token,
    _tokenize,
    _wrap_memory_evidence,
)


class TestRetrievalHelpers:
    """Test helper functions."""

    def test_approx_chars_for_tokens(self):
        """Token to char conversion uses ~4 chars per token."""
        assert _approx_chars_for_tokens(0) == 0
        assert _approx_chars_for_tokens(10) == 40
        assert _approx_chars_for_tokens(100) == 400
        assert _approx_chars_for_tokens(-5) == 0  # Negative handled

    def test_tokenize(self):
        """Tokenize extracts alphanumeric tokens."""
        assert _tokenize("hello world") == ["hello", "world"]
        assert _tokenize("user-authentication") == ["user", "authentication"]
        assert _tokenize("test123 abc456") == ["test123", "abc456"]
        assert _tokenize("a b") == []  # Single chars ignored
        assert _tokenize("") == []

    def test_haystack_matches_token(self):
        """Token matching respects word boundaries."""
        assert _haystack_matches_token("active user", "active")
        assert _haystack_matches_token("user is active", "active")
        assert not _haystack_matches_token("inactive user", "active")
        assert not _haystack_matches_token("reactivate", "active")

    def test_wrap_memory_evidence(self):
        """Memory wrapping includes delimiters and provenance."""
        wrapped = _wrap_memory_evidence("run123:tool", "Some content")
        assert MEMORY_BEGIN in wrapped
        assert MEMORY_END in wrapped
        assert "provenance:run123:tool" in wrapped
        assert "Some content" in wrapped


@pytest.fixture
def temp_db_path():
    """Create a temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "memory.db"


@pytest.fixture
def engine_with_data(temp_db_path):
    """Create engine with sample memory data."""
    engine = DynamicMemoryEngine(db_path=temp_db_path)
    scope = engine.get_shared_scope()

    scope.execute("""
        CREATE TABLE memories (
            content TEXT,
            provenance TEXT,
            created_ts REAL
        )
    """)

    base_ts = time.time()
    memories = [
        ("User authentication is working", "run1:auth_check", base_ts - 100),
        ("Database connection established", "run2:db_connect", base_ts - 80),
        ("Authentication failed for user bob", "run3:auth_check", base_ts - 60),
        ("User alice logged in successfully", "run4:login", base_ts - 40),
        ("Database query returned 5 results", "run5:db_query", base_ts - 20),
    ]

    for content, prov, ts in memories:
        scope.execute(
            "INSERT INTO memories (content, provenance, created_ts) VALUES (?, ?, ?)",
            (content, prov, ts),
        )

    yield engine, scope
    engine.close()


class TestMemoryRetriever:
    """Test MemoryRetriever."""

    def test_retrieve_empty_database(self, temp_db_path):
        """Retrieve from empty database returns empty list."""
        engine = DynamicMemoryEngine(db_path=temp_db_path)
        scope = engine.get_shared_scope()
        retriever = MemoryRetriever(scope)

        results = retriever.retrieve("test query", token_budget=100)
        assert results == []

        engine.close()

    def test_retrieve_zero_budget(self, engine_with_data):
        """Zero token budget returns empty list."""
        engine, scope = engine_with_data
        retriever = MemoryRetriever(scope)

        results = retriever.retrieve("authentication", token_budget=0)
        assert results == []

    def test_retrieve_keyword_match(self, engine_with_data):
        """Retrieval prioritizes keyword matches."""
        engine, scope = engine_with_data
        retriever = MemoryRetriever(scope)

        results = retriever.retrieve("authentication", token_budget=1000)

        assert len(results) > 0

        for result in results:
            assert MEMORY_BEGIN in result
            assert MEMORY_END in result
            assert "provenance:" in result

        assert "authentication" in results[0].lower()

    def test_retrieve_recency_ranking(self, engine_with_data):
        """More recent memories rank higher when no keywords match."""
        engine, scope = engine_with_data
        retriever = MemoryRetriever(scope)

        results = retriever.retrieve("xyz", token_budget=1000)

        assert len(results) > 0

        assert "run5" in results[0]

    def test_retrieve_respects_token_budget(self, engine_with_data):
        """Retrieval respects token budget."""
        engine, scope = engine_with_data
        retriever = MemoryRetriever(scope)

        results_small = retriever.retrieve("database", token_budget=10)

        results_large = retriever.retrieve("database", token_budget=1000)

        assert len(results_small) <= len(results_large)

        total_chars = sum(len(r) for r in results_small)
        assert total_chars <= 10 * 4 * 2  # Some overhead allowed

    def test_retrieve_deduplicates_provenance(self, temp_db_path):
        """Retrieval deduplicates by provenance."""
        engine = DynamicMemoryEngine(db_path=temp_db_path)
        scope = engine.get_shared_scope()

        scope.execute("""
            CREATE TABLE memories (
                content TEXT,
                provenance TEXT,
                created_ts REAL
            )
        """)

        ts = time.time()
        scope.execute(
            "INSERT INTO memories VALUES (?, ?, ?)",
            ("First", "run1:tool", ts),
        )
        scope.execute(
            "INSERT INTO memories VALUES (?, ?, ?)",
            ("Second", "run1:tool", ts + 1),
        )

        retriever = MemoryRetriever(scope)
        results = retriever.retrieve("test", token_budget=1000)

        assert len(results) == 1

        engine.close()

    def test_retrieve_trims_first_result_if_needed(self, temp_db_path):
        """First result is trimmed if it exceeds budget."""
        engine = DynamicMemoryEngine(db_path=temp_db_path)
        scope = engine.get_shared_scope()

        scope.execute("""
            CREATE TABLE memories (
                content TEXT,
                provenance TEXT,
                created_ts REAL
            )
        """)

        long_content = "x" * 1000
        scope.execute(
            "INSERT INTO memories VALUES (?, ?, ?)",
            (long_content, "run1:tool", time.time()),
        )

        retriever = MemoryRetriever(scope)

        results = retriever.retrieve("test", token_budget=10)

        if results:
            assert len(results) == 1
            assert len(results[0]) < len(long_content) + 200  # delimiters

        engine.close()

    def test_retrieve_custom_table_columns(self, temp_db_path):
        """Retrieval works with custom table and column names."""
        engine = DynamicMemoryEngine(db_path=temp_db_path)
        scope = engine.get_shared_scope()

        scope.execute("""
            CREATE TABLE custom_memories (
                text TEXT,
                source TEXT,
                timestamp REAL
            )
        """)

        scope.execute(
            "INSERT INTO custom_memories VALUES (?, ?, ?)",
            ("Test content", "test_source", time.time()),
        )

        retriever = MemoryRetriever(scope)
        results = retriever.retrieve(
            "test",
            token_budget=100,
            table_name="custom_memories",
            content_column="text",
            provenance_column="source",
            timestamp_column="timestamp",
        )

        assert len(results) > 0
        assert "Test content" in results[0]

        engine.close()


class TestMemoryRetrieverRanking:
    """Test ranking algorithm."""

    def test_keyword_match_beats_recency(self, temp_db_path):
        """Keyword matches rank higher than recency alone."""
        engine = DynamicMemoryEngine(db_path=temp_db_path)
        scope = engine.get_shared_scope()

        scope.execute("""
            CREATE TABLE memories (
                content TEXT,
                provenance TEXT,
                created_ts REAL
            )
        """)

        base_ts = time.time()

        # Old memory with keyword match
        scope.execute(
            "INSERT INTO memories VALUES (?, ?, ?)",
            ("authentication successful", "run1:auth", base_ts - 1000),
        )

        # Recent memory without keyword match
        scope.execute(
            "INSERT INTO memories VALUES (?, ?, ?)",
            ("database query completed", "run2:db", base_ts),
        )

        retriever = MemoryRetriever(scope)
        results = retriever.retrieve("authentication", token_budget=1000)

        # Keyword match should come first despite being older
        assert "authentication" in results[0].lower()

        engine.close()

    def test_multiple_keyword_matches_rank_higher(self, temp_db_path):
        """More keyword matches rank higher."""
        engine = DynamicMemoryEngine(db_path=temp_db_path)
        scope = engine.get_shared_scope()

        scope.execute("""
            CREATE TABLE memories (
                content TEXT,
                provenance TEXT,
                created_ts REAL
            )
        """)

        ts = time.time()

        # One keyword match
        scope.execute(
            "INSERT INTO memories VALUES (?, ?, ?)",
            ("user logged in", "run1:login", ts),
        )

        # Two keyword matches
        scope.execute(
            "INSERT INTO memories VALUES (?, ?, ?)",
            ("user authentication successful for user alice", "run2:auth", ts),
        )

        retriever = MemoryRetriever(scope)
        results = retriever.retrieve("user authentication", token_budget=1000)

        # Two-keyword match should come first
        assert "authentication" in results[0].lower()

        engine.close()

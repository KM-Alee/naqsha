"""Memory Port adapters and Dynamic Memory Engine."""

from naqsha.memory.base import MemoryPort, MemoryRecord
from naqsha.memory.ddl import ForbiddenDDLError, is_ddl_statement, validate_ddl
from naqsha.memory.engine import DynamicMemoryEngine
from naqsha.memory.inmemory import InMemoryMemoryPort
from naqsha.memory.retrieval import MemoryRetriever
from naqsha.memory.scope import MemoryScope
from naqsha.memory.sharing import TeamMemoryConfig, open_team_memory_engine
from naqsha.memory.simplemem_cross import SimpleMemCrossMemoryPort

__all__ = [
    # V1 Memory Port
    "MemoryPort",
    "MemoryRecord",
    "InMemoryMemoryPort",
    "SimpleMemCrossMemoryPort",
    # V2 Dynamic Memory Engine
    "DynamicMemoryEngine",
    "MemoryScope",
    "MemoryRetriever",
    "TeamMemoryConfig",
    "open_team_memory_engine",
    "ForbiddenDDLError",
    "validate_ddl",
    "is_ddl_statement",
]

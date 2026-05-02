"""SimpleMem-Cross Memory Port placeholder.

The adapter boundary is present so future work can map NAQSHA run lifecycle events
onto SimpleMem-Cross sessions without changing the Core Runtime.
"""

from __future__ import annotations


class SimpleMemCrossMemoryPort:
    def __init__(self, *_: object, **__: object) -> None:
        raise NotImplementedError(
            "SimpleMem-Cross integration is deferred until after the Runtime Slice."
        )

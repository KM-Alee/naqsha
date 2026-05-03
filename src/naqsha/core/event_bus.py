"""
Typed Event Bus implementation.

The RuntimeEventBus is the decoupling mechanism between the Core Runtime
and any UI, logging, or monitoring adapters. The core emits strongly-typed
Pydantic events; subscribers receive them asynchronously.
"""

import asyncio
from collections.abc import AsyncGenerator, Callable

from .events import RuntimeEvent


class RuntimeEventBus:
    """
    Event bus for runtime events.
    
    Supports synchronous emission and both synchronous and asynchronous subscription.
    Events are queued and delivered to all subscribers in order.
    """
    
    def __init__(self) -> None:
        self._subscribers: list[Callable[[RuntimeEvent], None]] = []
        self._event_queue: asyncio.Queue[RuntimeEvent] = asyncio.Queue()
        self._running = False
        
    def subscribe(self, handler: Callable[[RuntimeEvent], None]) -> None:
        """
        Subscribe to all events.
        
        Args:
            handler: Synchronous callback that receives each event.
        """
        self._subscribers.append(handler)
        
    def emit(self, event: RuntimeEvent) -> None:
        """
        Emit an event to all subscribers.
        
        This is a synchronous method that queues the event for delivery.
        Subscribers are called synchronously in order.
        
        Args:
            event: The event to emit.
        """
        # Deliver to synchronous subscribers immediately
        for handler in self._subscribers:
            try:
                handler(event)
            except Exception:
                # Subscribers must not break the event bus
                pass
                
        # Also queue for async consumers
        try:
            self._event_queue.put_nowait(event)
        except asyncio.QueueFull:
            # If queue is full, skip (this shouldn't happen with unbounded queue)
            pass
            
    async def events(self) -> AsyncGenerator[RuntimeEvent, None]:
        """
        Async generator that yields events as they are emitted.
        
        This is useful for async consumers like the TUI that want to
        process events in an event loop.
        
        Yields:
            RuntimeEvent instances as they are emitted.
        """
        while True:
            event = await self._event_queue.get()
            yield event
            
    def clear_subscribers(self) -> None:
        """Clear all subscribers. Useful for testing."""
        self._subscribers.clear()

"""Stream Handler for streaming agent responses.

Ported unchanged from ``backend/lib/agent_service/streaming/stream_handler.py``
(no AutoGen dependency).
"""

import asyncio
import logging
import time
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, List, Optional

from app.agents.schemas import StreamEvent, StreamEventType

logger = logging.getLogger(__name__)


class StreamHandler:
    """
    Handler for streaming events during agent orchestration.

    Provides async generator-based streaming for both:
    - Token-level streaming (from direct model calls)
    - Message-level streaming (from orchestrated conversations)

    Usage:
        handler = StreamHandler()

        # Subscribe to events
        async for event in handler.stream():
            print(event.content)

        # Or with callback
        handler.on_event(my_callback)

        # Emit events from orchestrator
        await handler.emit(StreamEvent(
            event_type=StreamEventType.MESSAGE,
            content="Hello!",
            source="Agent1"
        ))
    """

    def __init__(self):
        """Initialize the Stream Handler"""
        self._queue: asyncio.Queue[StreamEvent] = asyncio.Queue()
        self._callbacks: list[Callable[[StreamEvent], Awaitable[None]]] = []
        self._sync_callbacks: list[Callable[[StreamEvent], None]] = []
        self._is_active = False
        self._event_history: list[StreamEvent] = []
        self._max_history = 100
        logger.debug("Stream Handler initialized")

    async def emit(self, event: StreamEvent) -> None:
        """
        Emit a streaming event.

        Args:
            event: The event to emit
        """
        # Add timestamp if not set
        if event.timestamp is None:
            event.timestamp = time.time()

        # Add to history
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history.pop(0)

        # Put in queue for stream consumers
        await self._queue.put(event)

        # Notify callbacks
        await self._notify_callbacks(event)

        logger.debug(f"Emitted event: {event.event_type.value}")

    async def emit_token(self, token: str, source: Optional[str] = None) -> None:
        """
        Emit a token event.

        Args:
            token: The token string
            source: Optional source identifier
        """
        await self.emit(
            StreamEvent(
                event_type=StreamEventType.TOKEN,
                content=token,
                source=source,
            )
        )

    async def emit_message(
        self,
        content: str,
        source: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Emit a complete message event.

        Args:
            content: Message content
            source: Source agent name
            metadata: Optional metadata
        """
        await self.emit(
            StreamEvent(
                event_type=StreamEventType.MESSAGE,
                content=content,
                source=source,
                metadata=metadata or {},
            )
        )

    async def emit_status(
        self,
        status: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Emit a status event.

        Args:
            status: Status message
            metadata: Optional metadata
        """
        await self.emit(
            StreamEvent(
                event_type=StreamEventType.STATUS,
                content=status,
                metadata=metadata or {},
            )
        )

    async def emit_human_input_request(
        self,
        request_id: str,
        prompt: str,
        agent_name: str,
        options: Optional[List[str]] = None,
    ) -> None:
        """
        Emit a human input request event.

        Args:
            request_id: Unique request ID
            prompt: Prompt for the human
            agent_name: Name of requesting agent
            options: Optional predefined choices
        """
        await self.emit(
            StreamEvent(
                event_type=StreamEventType.HUMAN_INPUT_REQUEST,
                content=prompt,
                source=agent_name,
                metadata={
                    "request_id": request_id,
                    "options": options,
                },
            )
        )

    async def emit_error(
        self,
        error: str,
        source: Optional[str] = None,
    ) -> None:
        """
        Emit an error event.

        Args:
            error: Error message
            source: Optional source identifier
        """
        await self.emit(
            StreamEvent(
                event_type=StreamEventType.ERROR,
                content=error,
                source=source,
            )
        )

    async def stream(
        self,
        timeout: Optional[float] = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Async generator that yields streaming events.

        Args:
            timeout: Optional timeout between events

        Yields:
            StreamEvent objects as they are emitted
        """
        self._is_active = True

        try:
            while self._is_active:
                try:
                    if timeout:
                        event = await asyncio.wait_for(self._queue.get(), timeout=timeout)
                    else:
                        event = await self._queue.get()

                    yield event

                    # Check for terminal events
                    if event.event_type == StreamEventType.STATUS:
                        if event.content in ("completed", "aborted", "error"):
                            break

                except asyncio.TimeoutError:
                    # Yield a heartbeat/keep-alive
                    yield StreamEvent(
                        event_type=StreamEventType.STATUS,
                        content="heartbeat",
                    )
        finally:
            self._is_active = False

    def on_event(
        self,
        callback: Callable[[StreamEvent], Awaitable[None]],
    ) -> None:
        """
        Register an async callback for events.

        Args:
            callback: Async function receiving StreamEvent
        """
        self._callbacks.append(callback)

    def on_event_sync(
        self,
        callback: Callable[[StreamEvent], None],
    ) -> None:
        """
        Register a sync callback for events.

        Args:
            callback: Sync function receiving StreamEvent
        """
        self._sync_callbacks.append(callback)

    def stop(self) -> None:
        """Stop the stream"""
        self._is_active = False

    def get_history(self) -> list[StreamEvent]:
        """Get event history"""
        return self._event_history.copy()

    def clear_history(self) -> None:
        """Clear event history"""
        self._event_history.clear()

    async def _notify_callbacks(self, event: StreamEvent) -> None:
        """Notify all registered callbacks"""
        # Async callbacks
        for callback in self._callbacks:
            try:
                await callback(event)
            except Exception as e:
                logger.error(f"Stream callback error: {e}")

        # Sync callbacks
        loop = asyncio.get_event_loop()
        for callback in self._sync_callbacks:
            try:
                await loop.run_in_executor(None, callback, event)
            except Exception as e:
                logger.error(f"Sync stream callback error: {e}")


async def collect_stream(
    stream: AsyncGenerator[StreamEvent, None],
) -> list[StreamEvent]:
    """
    Utility to collect all events from a stream into a list.

    Args:
        stream: Async generator of StreamEvent

    Returns:
        List of all events
    """
    events = []
    async for event in stream:
        events.append(event)
    return events


async def filter_stream(
    stream: AsyncGenerator[StreamEvent, None],
    event_types: list[StreamEventType],
) -> AsyncGenerator[StreamEvent, None]:
    """
    Filter a stream to only yield specific event types.

    Args:
        stream: Source stream
        event_types: Event types to include

    Yields:
        Filtered StreamEvent objects
    """
    async for event in stream:
        if event.event_type in event_types:
            yield event

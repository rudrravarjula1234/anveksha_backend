"""Human Input Handler for Human-in-the-Loop orchestration.

Ported unchanged from ``backend/lib/agent_service/hitl/handler.py``
(no AutoGen dependency).
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, Optional

from app.agents.schemas import HumanInputRequest, HumanInputResponse

logger = logging.getLogger(__name__)


@dataclass
class PendingRequest:
    """Tracks a pending human input request"""

    request: HumanInputRequest
    event: asyncio.Event
    response: Optional[HumanInputResponse] = None
    created_at: float = field(default_factory=time.time)
    expired: bool = False


class HumanInputHandler:
    """
    Handles human-in-the-loop interactions during agent orchestration.

    Uses callback/event-based pattern where:
    1. Agent requests human input via request_input()
    2. External system receives callback notification
    3. External system submits response via submit_response()
    4. Agent continues with human's input

    Usage:
        handler = HumanInputHandler()

        # Register callback for human input requests
        handler.register_callback(my_notification_callback)

        # In orchestration, agent calls:
        response = await handler.request_input(request)

        # External system (API, WebSocket, etc.) calls:
        handler.submit_response(request_id, response)
    """

    def __init__(self, default_timeout: int = 300):
        """
        Initialize the Human Input Handler.

        Args:
            default_timeout: Default timeout in seconds for human responses
        """
        self.default_timeout = default_timeout
        self._pending_requests: Dict[str, PendingRequest] = {}
        self._callbacks: list[Callable[[HumanInputRequest], Awaitable[None]]] = []
        self._sync_callbacks: list[Callable[[HumanInputRequest], None]] = []
        logger.info("Human Input Handler initialized")

    def register_callback(
        self,
        callback: Callable[[HumanInputRequest], Awaitable[None]],
    ) -> None:
        """
        Register an async callback for human input request notifications.

        The callback will be called whenever an agent requests human input,
        allowing external systems to be notified and prompt the human.

        Args:
            callback: Async function that receives HumanInputRequest
        """
        self._callbacks.append(callback)
        logger.debug(f"Registered async callback, total: {len(self._callbacks)}")

    def register_sync_callback(
        self,
        callback: Callable[[HumanInputRequest], None],
    ) -> None:
        """
        Register a synchronous callback for human input request notifications.

        Args:
            callback: Sync function that receives HumanInputRequest
        """
        self._sync_callbacks.append(callback)
        logger.debug(f"Registered sync callback, total: {len(self._sync_callbacks)}")

    def unregister_callback(
        self,
        callback: Callable[[HumanInputRequest], Awaitable[None]],
    ) -> bool:
        """
        Unregister a previously registered callback.

        Args:
            callback: The callback to remove

        Returns:
            True if callback was found and removed
        """
        try:
            self._callbacks.remove(callback)
            return True
        except ValueError:
            return False

    async def request_input(
        self,
        request: HumanInputRequest,
        timeout: Optional[int] = None,
    ) -> HumanInputResponse:
        """
        Request input from a human and wait for response.

        This method blocks (async) until:
        1. Human provides a response via submit_response()
        2. Timeout is reached

        Args:
            request: The human input request details
            timeout: Optional timeout override (uses request.timeout_seconds if None)

        Returns:
            HumanInputResponse with human's input

        Raises:
            asyncio.TimeoutError: If human doesn't respond within timeout
        """
        timeout_seconds = timeout or request.timeout_seconds or self.default_timeout

        # Create pending request with event
        event = asyncio.Event()
        pending = PendingRequest(request=request, event=event)
        self._pending_requests[request.request_id] = pending

        logger.info(f"Human input requested: {request.request_id}")
        logger.debug(f"Prompt: {request.prompt_for_human[:100]}...")

        # Notify callbacks
        await self._notify_callbacks(request)

        try:
            # Wait for response with timeout
            await asyncio.wait_for(event.wait(), timeout=timeout_seconds)

            response = pending.response
            if response is None:
                raise RuntimeError(f"Event set but no response for {request.request_id}")

            logger.info(f"Human response received: {request.request_id}")
            return response

        except asyncio.TimeoutError:
            pending.expired = True
            logger.warning(f"Human input timeout: {request.request_id}")
            # Return a timeout response
            return HumanInputResponse(
                request_id=request.request_id,
                content="",
                action="timeout",
                metadata={"error": "Human input timeout exceeded"},
            )
        finally:
            # Cleanup
            self._cleanup_request(request.request_id)

    def submit_response(
        self,
        request_id: str,
        response: HumanInputResponse,
    ) -> bool:
        """
        Submit a human's response to a pending request.

        Called by external systems (API endpoints, WebSocket handlers, etc.)
        when human provides their input.

        Args:
            request_id: ID of the original request
            response: Human's response

        Returns:
            True if response was accepted, False if request not found/expired
        """
        pending = self._pending_requests.get(request_id)

        if pending is None:
            logger.warning(f"No pending request found: {request_id}")
            return False

        if pending.expired:
            logger.warning(f"Request already expired: {request_id}")
            return False

        # Store response and signal event
        pending.response = response
        pending.event.set()

        logger.info(f"Human response submitted: {request_id}")
        return True

    def get_pending_requests(self) -> list[HumanInputRequest]:
        """
        Get all currently pending human input requests.

        Returns:
            List of pending HumanInputRequest objects
        """
        return [
            pending.request
            for pending in self._pending_requests.values()
            if not pending.expired
        ]

    def get_pending_request(self, request_id: str) -> Optional[HumanInputRequest]:
        """
        Get a specific pending request by ID.

        Args:
            request_id: The request ID

        Returns:
            HumanInputRequest if found and not expired, None otherwise
        """
        pending = self._pending_requests.get(request_id)
        if pending and not pending.expired:
            return pending.request
        return None

    def cancel_request(self, request_id: str) -> bool:
        """
        Cancel a pending request.

        Args:
            request_id: The request to cancel

        Returns:
            True if request was cancelled
        """
        pending = self._pending_requests.get(request_id)
        if pending and not pending.expired:
            pending.expired = True
            pending.response = HumanInputResponse(
                request_id=request_id,
                content="",
                action="cancelled",
                metadata={"reason": "Request cancelled"},
            )
            pending.event.set()
            logger.info(f"Request cancelled: {request_id}")
            return True
        return False

    async def _notify_callbacks(self, request: HumanInputRequest) -> None:
        """Notify all registered callbacks about a new request"""
        # Async callbacks
        for callback in self._callbacks:
            try:
                await callback(request)
            except Exception as e:
                logger.error(f"Callback error: {e}")

        # Sync callbacks (run in executor to not block)
        loop = asyncio.get_event_loop()
        for callback in self._sync_callbacks:
            try:
                await loop.run_in_executor(None, callback, request)
            except Exception as e:
                logger.error(f"Sync callback error: {e}")

    def _cleanup_request(self, request_id: str) -> None:
        """Remove a request from pending"""
        if request_id in self._pending_requests:
            del self._pending_requests[request_id]
            logger.debug(f"Cleaned up request: {request_id}")

    def cleanup_expired(self) -> int:
        """
        Clean up all expired requests.

        Returns:
            Number of requests cleaned up
        """
        now = time.time()
        expired_ids = [
            req_id
            for req_id, pending in self._pending_requests.items()
            if pending.expired or (now - pending.created_at) > pending.request.timeout_seconds
        ]

        for req_id in expired_ids:
            self._cleanup_request(req_id)

        return len(expired_ids)

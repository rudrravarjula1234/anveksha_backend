"""WebSocket connection hub for real-time workflow events.

Keyed by user id; a user may have multiple live sockets (tabs). Temporal
notification activities publish completion/failure events here so the
frontend can react when a durable workflow finishes. Pure in-process —
no Temporal dependency, so it's unit-testable on its own.
"""

import json
import logging
from typing import Any

log = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        # user_id -> list of connected sockets. Typed loosely so this module
        # has no hard dependency on starlette's WebSocket for testing.
        self._connections: dict[str, list[Any]] = {}

    async def connect(self, user_id: str, websocket: Any) -> None:
        await websocket.accept()
        self._connections.setdefault(user_id, []).append(websocket)
        log.info("WS connect user=%s (total=%d)", user_id, len(self._connections[user_id]))

    def disconnect(self, user_id: str, websocket: Any) -> None:
        conns = self._connections.get(user_id, [])
        if websocket in conns:
            conns.remove(websocket)
        if not conns:
            self._connections.pop(user_id, None)

    def connection_count(self, user_id: str) -> int:
        return len(self._connections.get(user_id, []))

    async def send_to_user(self, user_id: str, data: dict[str, Any]) -> int:
        """Push a JSON message to every live socket for a user.

        Returns the number of sockets the message was delivered to. Dead
        sockets are pruned.
        """
        conns = self._connections.get(user_id, [])
        delivered = 0
        dead: list[Any] = []
        for ws in conns:
            try:
                await ws.send_text(json.dumps(data))
                delivered += 1
            except Exception:  # noqa: BLE001 — a dead socket shouldn't break the loop
                dead.append(ws)
        for ws in dead:
            self.disconnect(user_id, ws)
        return delivered


# Module-level singleton — imported by the workflow notification activities
# and the /api/workflows/ws endpoint.
connection_manager = ConnectionManager()

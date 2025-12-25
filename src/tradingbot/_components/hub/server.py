"""WebSocket Server for remote UI clients.

Provides a WebSocket interface for external clients (web, mobile) to
receive real-time trading updates. Clients receive a full state
snapshot on connect, then incremental updates via channels.
"""

import asyncio
import json
import logging
from typing import Any

from .hub import EventHub

logger = logging.getLogger(__name__)

# Optional websockets import - gracefully handle if not installed
try:
    import websockets
    from websockets.asyncio.server import Server, ServerConnection

    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    Server = Any  # type: ignore[misc,assignment]
    ServerConnection = Any  # type: ignore[misc,assignment]


class HubServer:
    """WebSocket server for remote UI clients.

    Protocol:
        On connect: Server sends {"type": "snapshot", "data": GlobalState}
        Updates: Server sends {"channel": "ticker", "data": {...}}
        Client can send: {"ping": true} -> Server responds {"pong": true}

    Usage:
        hub = EventHub()
        server = HubServer(hub)
        await server.start()
        # ... trading runs ...
        await server.stop()
    """

    def __init__(
        self,
        hub: EventHub,
        host: str = "127.0.0.1",
        port: int = 8765,
    ) -> None:
        if not WEBSOCKETS_AVAILABLE:
            raise ImportError("websockets package not installed. Install with: uv add websockets")

        self.hub = hub
        self.host = host
        self.port = port
        self._server: Server | None = None
        self._running = False

    async def start(self) -> None:
        """Start WebSocket server."""
        if self._running:
            return

        self._server = await websockets.serve(
            self._handle_client,
            self.host,
            self.port,
        )
        self._running = True
        logger.info(f"WebSocket server started on ws://{self.host}:{self.port}")

    async def stop(self) -> None:
        """Stop WebSocket server."""
        if not self._running or not self._server:
            return

        self._server.close()
        await self._server.wait_closed()
        self._running = False
        logger.info("WebSocket server stopped")

    @property
    def is_running(self) -> bool:
        """Check if server is running."""
        return self._running

    @property
    def url(self) -> str:
        """Get WebSocket URL."""
        return f"ws://{self.host}:{self.port}"

    async def _handle_client(self, websocket: ServerConnection) -> None:
        """Handle new client connection."""
        try:
            client_addr = websocket.remote_address
        except Exception:
            client_addr = "unknown"

        logger.info(f"Client connected: {client_addr}")

        # Register with hub for broadcasts
        self.hub.add_websocket(websocket)

        try:
            # Send full state snapshot
            state = self.hub.get_state()
            snapshot = {
                "type": "snapshot",
                "data": state.to_dict(),
            }
            await websocket.send(json.dumps(snapshot))

            # Keep connection alive, handle client messages
            async for message in websocket:
                await self._handle_message(websocket, message)

        except websockets.ConnectionClosed:
            logger.debug(f"Client disconnected: {client_addr}")
        except Exception as e:
            logger.debug(f"Client error: {client_addr} - {e}")
        finally:
            self.hub.remove_websocket(websocket)

    async def _handle_message(
        self,
        websocket: ServerConnection,
        message: str | bytes,
    ) -> None:
        """Handle client messages."""
        if isinstance(message, bytes):
            message = message.decode("utf-8")
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return

        # Ping/pong for keepalive
        if data.get("ping"):
            await websocket.send(json.dumps({"pong": True}))
            return

        # Request full state refresh
        if data.get("refresh"):
            state = self.hub.get_state()
            snapshot = {
                "type": "snapshot",
                "data": state.to_dict(),
            }
            await websocket.send(json.dumps(snapshot))
            return


async def run_server(
    hub: EventHub,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    """Run WebSocket server until cancelled.

    Usage:
        hub = EventHub()
        task = asyncio.create_task(run_server(hub))
        # ... later ...
        task.cancel()
    """
    server = HubServer(hub, host, port)
    await server.start()

    try:
        # Run forever until cancelled
        await asyncio.Future()
    except asyncio.CancelledError:
        pass
    finally:
        await server.stop()

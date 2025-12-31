"""WebSocket Server for remote UI clients.

Provides a WebSocket interface for external clients (web, mobile) to
receive real-time trading updates. Clients receive a full state
snapshot on connect, then incremental updates via channels.

Also provides an optional HTTP server for serving static web interface files.
"""

import asyncio
import json
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any

from tradingbot._components.logging import get_logger

from .hub import EventHub

logger = get_logger(__name__)

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
        *,
        serve_web: bool = False,
        web_port: int | None = None,
        web_dir: Path | None = None,
    ) -> None:
        if not WEBSOCKETS_AVAILABLE:
            raise ImportError("websockets package not installed. Install with: uv add websockets")

        self.hub = hub
        self.host = host
        self.port = port
        self._server: Server | None = None
        self._running = False

        # HTTP server for web interface
        self._serve_web = serve_web
        self._web_port = web_port or (port - 1)  # Default to WS port - 1 (e.g., 8764)
        self._web_dir = web_dir or self._find_web_dir()
        self._http_server: HTTPServer | None = None
        self._http_thread: threading.Thread | None = None

    def _find_web_dir(self) -> Path:
        """Find the web/dist directory."""
        # Start from this file and go up to find web/dist
        current = Path(__file__).resolve()
        for _ in range(10):  # Go up max 10 levels
            current = current.parent
            web_dist = current / "web" / "dist"
            if web_dist.exists():
                return web_dist
        return Path("web/dist")  # Fallback

    async def start(self) -> None:
        """Start WebSocket server and optionally HTTP server for web interface."""
        if self._running:
            return

        self._server = await websockets.serve(
            self._handle_client,
            self.host,
            self.port,
        )
        self._running = True
        logger.info(f"WebSocket server started on ws://{self.host}:{self.port}")

        # Start HTTP server for web interface if enabled
        if self._serve_web:
            self._start_http_server()

    async def stop(self) -> None:
        """Stop WebSocket server and HTTP server."""
        if not self._running or not self._server:
            return

        # Stop HTTP server first
        self._stop_http_server()

        self._server.close()
        await self._server.wait_closed()
        self._running = False
        logger.info("WebSocket server stopped")

    def _start_http_server(self) -> None:
        """Start HTTP server for static web files in background thread."""
        if not self._web_dir.exists():
            logger.warning(f"Web directory not found: {self._web_dir}")
            return

        # Custom handler that serves from web_dir and suppresses logging
        class SilentHandler(SimpleHTTPRequestHandler):
            def __init__(handler_self, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, directory=str(self._web_dir), **kwargs)

            def log_message(handler_self, format: str, *args: Any) -> None:
                pass  # Suppress HTTP request logging

            def do_GET(handler_self) -> None:
                # Handle SPA routing - serve index.html for non-file paths
                path = handler_self.path.split("?")[0]
                file_path = self._web_dir / path.lstrip("/")
                if not file_path.exists() and not path.startswith("/assets"):
                    handler_self.path = "/index.html"
                super().do_GET()

        try:
            self._http_server = HTTPServer((self.host, self._web_port), SilentHandler)
            self._http_thread = threading.Thread(
                target=self._http_server.serve_forever,
                daemon=True,
            )
            self._http_thread.start()
            logger.info(f"Web interface available at http://{self.host}:{self._web_port}")
        except Exception as e:
            logger.error(f"Failed to start HTTP server: {e}")

    def _stop_http_server(self) -> None:
        """Stop HTTP server."""
        if self._http_server:
            self._http_server.shutdown()
            self._http_server = None
            self._http_thread = None
            logger.info("HTTP server stopped")

    @property
    def is_running(self) -> bool:
        """Check if server is running."""
        return self._running

    @property
    def url(self) -> str:
        """Get WebSocket URL."""
        return f"ws://{self.host}:{self.port}"

    @property
    def web_url(self) -> str | None:
        """Get web interface URL if serving and HTTP server is running."""
        if self._serve_web and self._http_server is not None:
            return f"http://{self.host}:{self._web_port}"
        return None

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
    *,
    serve_web: bool = False,
    web_port: int | None = None,
) -> None:
    """Run WebSocket server until cancelled.

    Args:
        hub: EventHub instance to broadcast from.
        host: Host to bind to.
        port: WebSocket port.
        serve_web: If True, also serve web interface on web_port.
        web_port: HTTP port for web interface (default: port - 1).

    Usage:
        hub = EventHub()
        task = asyncio.create_task(run_server(hub, serve_web=True))
        # ... later ...
        task.cancel()
    """
    server = HubServer(hub, host, port, serve_web=serve_web, web_port=web_port)
    await server.start()

    try:
        # Run forever until cancelled
        await asyncio.Future()
    except asyncio.CancelledError:
        pass
    finally:
        await server.stop()

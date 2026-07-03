"""WebSocket client for communicating with MuseScore."""

import websockets
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("MuseScoreMCP.Client")


class MuseScoreClient:
    """Client to communicate with MuseScore WebSocket API."""
    
    def __init__(self, host: str = "localhost", port: int = 8765):
        self.uri = f"ws://{host}:{port}"
        self.websocket = None
    
    async def connect(self):
        """Connect to the MuseScore WebSocket API."""
        try:
            self.websocket = await websockets.connect(self.uri)
            logger.info(f"Connected to MuseScore API at {self.uri}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to MuseScore API: {str(e)}")
            return False
    
    async def _reset_socket(self):
        """Drop the current socket so the next call reconnects from scratch.

        MuseScore restarting (or the plugin reloading) leaves us holding a dead
        socket whose send/recv raises. Nulling it here lets send_command pick up
        a fresh connection without the whole MCP server needing a restart.
        """
        if self.websocket is not None:
            try:
                await self.websocket.close()
            except Exception:
                pass
            self.websocket = None

    async def send_command(self, action: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send a command to MuseScore and wait for response.

        Tries the existing socket first; if that fails (e.g. MuseScore was
        restarted and the socket is stale), the socket is dropped and the
        command is retried once on a fresh connection.
        """
        if params is None:
            params = {}

        command = {"action": action, "params": params}
        payload = json.dumps(command)

        last_error: Optional[str] = None
        for attempt in range(2):
            if not self.websocket:
                if not await self.connect():
                    return {"error": "Not connected to MuseScore"}

            try:
                logger.info(f"Sending command: {payload}")
                await self.websocket.send(payload)
                response = await self.websocket.recv()
                logger.info(f"Received response: {response}")
                return json.loads(response)
            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"Send failed (attempt {attempt + 1}/2), resetting socket: {last_error}"
                )
                await self._reset_socket()

        return {"error": f"Not connected to MuseScore: {last_error}"}

    async def close(self):
        """Close the WebSocket connection."""
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
            logger.info("Disconnected from MuseScore API")
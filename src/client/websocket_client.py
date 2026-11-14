"""WebSocket client for the MuseScore plugin.

The plugin runs a WebSocket server inside MuseScore. The client sends it JSON
commands ({"action": ..., "params": {...}}) and reads its JSON replies.
"""

import json
import logging
from typing import Any, Dict, Optional

import websockets
from fastmcp.exceptions import ToolError

logger = logging.getLogger("MuseScoreMCP.Client")


def unwrap_result(response: dict) -> dict:
    """Return the plugin's result payload, or raise ToolError on an error.

    The plugin replies {"status": "success", "result": {...}}; handler errors arrive
    either as {"status": "error", "message": ...} or as result.error.

    Args:
        response (dict): The plugin's reply, as returned by
            MuseScoreClient.send_command.

    Returns:
        result (dict): The "result" part of a successful reply.

    Raises:
        ToolError: If the reply reports an error, or has no result
            dictionary.
    """
    if response.get("status") == "error" or "error" in response:
        raise ToolError(
            response.get("message")
            or response.get("error")
            or "MuseScore error"
        )
    result = response.get("result")
    if not isinstance(result, dict) or "error" in result:
        message = (
            result.get("error")
            if isinstance(result, dict)
            else "Unexpected plugin response"
        )
        raise ToolError(message)
    return result


class MuseScoreClient:
    """A connection to the MuseScore plugin's WebSocket server.

    The client connects on first use, and reconnects once when a command fails
    on a stale connection (for example after MuseScore was restarted).

    Attributes:
        uri (str): The plugin's WebSocket address, e.g. "ws://localhost:8765".
        websocket (Optional[ClientConnection]): The open connection, or None when
            not connected.

    Example:
        >>> client = MuseScoreClient()
        >>> client.uri
        'ws://localhost:8765'
        >>> client.websocket is None
        True
    """

    def __init__(self, host: str = "localhost", port: int = 8765) -> None:
        """Prepare a client for the plugin; it connects on first use.

        Args:
            host (str): The host the plugin's server listens on.
            port (int): The port the plugin's server listens on.
        """
        self.uri = f"ws://{host}:{port}"
        self.websocket = None

    async def connect(self) -> bool:
        """Connect to the plugin's WebSocket server.

        A failed connection is logged, not raised.

        Returns:
            connected (bool): True if the connection was made, False if not.
        """
        try:
            # Score analyses of large scores can exceed the 1 MiB default frame limit.
            self.websocket = await websockets.connect(self.uri, max_size=None)
            logger.info(f"Connected to MuseScore API at {self.uri}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to MuseScore API: {str(e)}")
            return False

    async def _reset_socket(self) -> None:
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

    async def send_command(
        self, action: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Send a command to the plugin and wait for its reply.

        Tries the existing socket first; if that fails (e.g. MuseScore was
        restarted and the socket is stale), the socket is dropped and the
        command is retried once on a fresh connection.

        Args:
            action (str): The plugin action to run, e.g. "getScore".
            params (Optional[Dict[str, Any]]): The action's parameters. Defaults
                to no parameters.

        Returns:
            response (Dict[str, Any]): The plugin's parsed reply, or
                {"error": ...} if MuseScore could not be reached.
        """
        if params is None:
            params = {}

        command = {"action": action, "params": params}
        payload = json.dumps(command)

        last_error: Optional[str] = None
        for attempt in range(2):
            if not self.websocket:
                await self.connect()
            websocket = self.websocket  # None if connecting failed
            if websocket is None:
                return {"error": "Not connected to MuseScore"}

            try:
                logger.info(f"Sending command: {payload}")
                await websocket.send(payload)
                response = await websocket.recv()
                logger.info(f"Received response: {response}")
                return json.loads(response)
            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"Send failed (attempt {attempt + 1}/2), resetting socket: {last_error}"
                )
                await self._reset_socket()

        return {"error": f"Not connected to MuseScore: {last_error}"}

    async def request(
        self, action: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Send a command and return its result, raising ToolError on failure.

        Args:
            action (str): The plugin action to run, e.g. "getScore".
            params (Optional[Dict[str, Any]]): The action's parameters. Defaults
                to no parameters.

        Returns:
            result (Dict[str, Any]): The "result" part of the plugin's reply.

        Raises:
            ToolError: If MuseScore cannot be reached or the plugin reports an
                error.
        """
        return unwrap_result(await self.send_command(action, params))

    async def close(self) -> None:
        """Close the connection to the plugin, if one is open."""
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
            logger.info("Disconnected from MuseScore API")

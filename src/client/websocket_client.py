"""WebSocket client for the MuseScore plugin.

The plugin runs a WebSocket server inside MuseScore. The client sends it JSON
commands ({"action": ..., "params": {...}}) and reads its JSON replies.
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, Optional

import websockets
from fastmcp.exceptions import ToolError

logger = logging.getLogger("MuseScoreMCP.Client")

DEFAULT_TIMEOUT = 60.0
"""Seconds to wait for the plugin's reply; MUSESCORE_TIMEOUT overrides it."""


def unwrap_result(response: dict) -> dict:
    """Return the plugin's result payload, or raise ToolError on an error.

    The plugin replies {"status": "success", "result": {...}}; handler errors
    arrive either as {"status": "error", "message": ...} or as result.error.

    Args:
        response (dict): The plugin's reply, as returned by
            MuseScoreClient.send_command.

    Returns:
        result (dict): The "result" part of a successful reply.

    Raises:
        ToolError: If the reply reports an error, or has no result dictionary.
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

    The client connects on first use and sends one command at a time. When a
    command cannot be sent on a stale connection (for example after MuseScore
    was restarted), it reconnects and sends it once more. A command that was
    sent is never sent again, so a lost reply cannot apply it twice.

    Attributes:
        uri (str): The plugin's WebSocket address, e.g. "ws://localhost:8765".
        websocket (Optional[ClientConnection]): The open connection, or None
            when not connected.
        timeout (float): Seconds to wait for the plugin's reply.

    Example:
        >>> client = MuseScoreClient()
        >>> client.uri
        'ws://localhost:8765'
        >>> client.websocket is None
        True
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8765,
        timeout: Optional[float] = None,
    ) -> None:
        """Prepare a client for the plugin; it connects on first use.

        Args:
            host (str): The host the plugin's server listens on.
            port (int): The port the plugin's server listens on.
            timeout (Optional[float]): Seconds to wait for a reply. Defaults to
                $MUSESCORE_TIMEOUT, or DEFAULT_TIMEOUT when that is not set.
        """
        self.uri = f"ws://{host}:{port}"
        self.websocket = None
        self.timeout = (
            timeout
            if timeout is not None
            else float(os.environ.get("MUSESCORE_TIMEOUT", DEFAULT_TIMEOUT))
        )
        self._lock: Optional[asyncio.Lock] = None
        self._lock_loop: Optional[asyncio.AbstractEventLoop] = None

    def _command_lock(self) -> asyncio.Lock:
        """Return the lock that lets one command at a time use the socket.

        The plugin answers commands in order on one connection, so a second
        command must wait until the first one's reply has been read. The lock is
        made per event loop, because the client outlives a single loop in the
        tests.

        Returns:
            lock (asyncio.Lock): The lock for the running event loop.
        """
        loop = asyncio.get_running_loop()
        if self._lock is None or self._lock_loop is not loop:
            self._lock = asyncio.Lock()
            self._lock_loop = loop
        return self._lock

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

        Commands wait for each other, so each reply is read by the command it
        belongs to. If the command cannot be sent (e.g. MuseScore was restarted
        and the socket is stale), the socket is dropped and the command is sent
        once more on a fresh connection. Once sent, it is never sent again: if
        no reply comes within the timeout, or the connection is lost, the reply
        is an error and the socket is dropped.

        Args:
            action (str): The plugin action to run, e.g. "getScore".
            params (Optional[Dict[str, Any]]): The action's parameters. Defaults
                to no parameters.

        Returns:
            response (Dict[str, Any]): The plugin's parsed reply, or {"error":
                ...} if MuseScore could not be reached, did not answer in time,
                or the connection was lost after sending.
        """
        async with self._command_lock():
            return await self._send_command(action, params)

    async def _send_command(
        self, action: str, params: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Send a command and read its reply; the caller holds the lock.

        Args:
            action (str): The plugin action to run.
            params (Optional[Dict[str, Any]]): The action's parameters.

        Returns:
            response (Dict[str, Any]): As for send_command.
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
            except Exception as e:
                # Not sent, so it is safe to try again on a fresh connection
                # (e.g. MuseScore was restarted and the socket is stale).
                last_error = str(e)
                logger.warning(
                    f"Send failed (attempt {attempt + 1}/2), resetting socket: {last_error}"
                )
                await self._reset_socket()
                continue

            # Sent: from here on, never send it again, which could apply it twice.
            try:
                response = await asyncio.wait_for(
                    websocket.recv(), self.timeout
                )
            except TimeoutError:
                # A late reply would be read as the next command's reply.
                await self._reset_socket()
                return {
                    "error": f"MuseScore did not answer within {self.timeout:g} s. "
                    "It may be busy or showing a dialog; check MuseScore."
                }
            except Exception as e:
                await self._reset_socket()
                return {
                    "error": f"The connection to MuseScore was lost after sending "
                    f"{action!r} ({e}). The command may have been applied; check "
                    "the score before repeating it."
                }
            logger.info(f"Received response: {response}")
            return json.loads(response)

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

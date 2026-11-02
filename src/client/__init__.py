"""WebSocket client for MuseScore communication."""

from .websocket_client import MuseScoreClient, unwrap_result

__all__ = ["MuseScoreClient", "unwrap_result"]
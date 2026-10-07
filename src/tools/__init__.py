"""MCP tools for MuseScore operations."""

from .connection import setup_connection_tools
from .navigation import setup_navigation_tools
from .notes_measures import setup_notes_measures_tools
from .staff_instruments import setup_staff_instruments_tools
from .time_tempo import setup_time_tempo_tools
from .sequences import setup_sequence_tools
from .viewer import setup_viewer_tools

__all__ = [
    "setup_connection_tools",
    "setup_navigation_tools", 
    "setup_notes_measures_tools",
    "setup_staff_instruments_tools",
    "setup_time_tempo_tools",
    "setup_sequence_tools",
    "setup_viewer_tools",
]
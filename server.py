from fastmcp import FastMCP
import sys
import logging

# Import modular components
from src.client import MuseScoreClient
from src.tools import (
    setup_connection_tools,
    setup_navigation_tools,
    setup_notes_measures_tools,
    setup_staff_instruments_tools,
    setup_time_tempo_tools,
    setup_sequence_tools,
    setup_viewer_tools,
)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger("MuseScoreMCP")

# Create the MCP app and client
mcp = FastMCP("MuseScore Assistant")
client = MuseScoreClient()

# Setup all tool categories
setup_connection_tools(mcp, client)
setup_navigation_tools(mcp, client)
setup_notes_measures_tools(mcp, client)
setup_staff_instruments_tools(mcp, client)
setup_time_tempo_tools(mcp, client)
setup_sequence_tools(mcp, client)
setup_viewer_tools(mcp, client)

# Main entry point
if __name__ == "__main__":
    mcp.run()
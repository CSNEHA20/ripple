"""Ripple MCP Server entrypoint.
Enables running the MCP server directly via `python mcp_server.py`.
"""

from app.mcp_server import mcp_server, run_stdio

if __name__ == "__main__":
    run_stdio()

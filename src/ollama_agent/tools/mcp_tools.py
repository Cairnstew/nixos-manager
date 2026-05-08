"""
MCP tool integrations for ollama_agent.

mcp-nixos is installed as a direct dependency (uv add mcp-nixos) so
the mcp-nixos executable is always available on PATH in the venv.
"""

from __future__ import annotations

import logging

from smolagents import Tool
from smolagents.mcp_client import MCPClient

logger = logging.getLogger(__name__)


def get_mcp_nixos_tools(transport: str = "stdio") -> list[Tool]:
    """Return smolagents tools backed by the mcp-nixos MCP server.

    Args:
        transport: ``"stdio"`` (default, spawns mcp-nixos directly) or
                   ``"http"`` (connects to a running HTTP instance on port 8001).
    """
    if transport == "http":
        return get_mcp_tools_from_url("http://127.0.0.1:8001/mcp")
    return get_mcp_tools_from_command("mcp-nixos")


def get_mcp_tools_from_url(url: str) -> list[Tool]:
    """Connect to any HTTP MCP server and return its tools.

    Args:
        url: Full MCP endpoint URL, e.g. ``"http://localhost:8001/mcp"``.
    """
    client = MCPClient(
        {"url": url, "transport": "streamable-http"},
        structured_output=False,
    )
    tools = client.get_tools()
    logger.info("Loaded %d tools from %s", len(tools), url)
    return tools


def get_mcp_tools_from_command(command: str, *args: str) -> list[Tool]:
    """Spawn any stdio MCP server and return its tools.

    Args:
        command: Executable to run, e.g. ``"mcp-nixos"``.
        *args: Any additional arguments to pass.
    """
    try:
        from mcp import StdioServerParameters
    except ImportError as e:
        raise ImportError(
            "Please install the mcp extra: pip install 'smolagents[mcp]'"
        ) from e

    params = StdioServerParameters(command=command, args=list(args))
    client = MCPClient(params, structured_output=False)
    tools = client.get_tools()
    logger.info("Loaded %d tools from '%s %s'", len(tools), command, " ".join(args))
    return tools
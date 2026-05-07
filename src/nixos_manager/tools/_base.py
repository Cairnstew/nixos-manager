import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass


async def _call_mcp_async(tool_name: str, payload: dict) -> str:
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_nixos.server"],
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, payload)
            return "\n".join(
                b.text for b in result.content if hasattr(b, "text")
            )


def run_mcp(tool_name: str, payload: dict) -> str:
    try:
        return asyncio.run(_call_mcp_async(tool_name, payload))
    except Exception as e:
        return f"MCP error: {e}"


def parse_params(params: str | dict) -> dict:
    if isinstance(params, str):
        try:
            return json.loads(params)
        except Exception:
            return {}
    return params or {}


def out(data: dict) -> str:
    return json.dumps(data, indent=2)
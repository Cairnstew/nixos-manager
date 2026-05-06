import json
import asyncio
import sys
import nest_asyncio

from qwen_agent.tools.base import BaseTool, register_tool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

nest_asyncio.apply()


@register_tool('nix_search_tool')
class NixSearchTool(BaseTool):
    description = 'Search for NixOS options, packages, and documentation.'
    parameters = [{
        'name': 'query',
        'type': 'string',
        'description': 'The package name or NixOS option to look up (e.g., "services.nginx" or "python3").',
        'required': True
    }]

    _session = None

    async def _get_session(self):
        if NixSearchTool._session is None:
            server_params = StdioServerParameters(
                command=sys.executable,
                args=["-m", "mcp_nixos.server"],  # ← key fix
            )

            read, write = await stdio_client(server_params).__aenter__()
            session = await ClientSession(read, write).__aenter__()
            await session.initialize()

            NixSearchTool._session = session

        return NixSearchTool._session

    async def _call_mcp(self, query: str):
        session = await self._get_session()
        result = await session.call_tool("nix", {   # ← also fix this
            "action": "search",
            "query": query
        })

        return "\n".join(
            block.text for block in result.content
            if hasattr(block, "text")
        )

    def call(self, params: str, **kwargs) -> str:
        params = json.loads(params)
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self._call_mcp(params['query']))
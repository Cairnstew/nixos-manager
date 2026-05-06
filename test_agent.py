# check_tools.py
import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    # Use the current interpreter (Nix Python), not uvx
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_nixos.server"],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            for tool in tools.tools:
                print(f"name: {tool.name}")
                print(f"description: {tool.description}")
                print(f"inputs: {tool.inputSchema}")
                print("---")


if __name__ == "__main__":
    asyncio.run(main())
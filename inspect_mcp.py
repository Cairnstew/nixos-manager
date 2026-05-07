import asyncio
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_nixos.server"],
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("\n--- Available MCP Tools ---")
            for tool in tools.tools:
                print(f"Name: {tool.name}")
                print(f"Arguments: {tool.inputSchema}")
                print("-" * 25)

if __name__ == "__main__":
    asyncio.run(main())
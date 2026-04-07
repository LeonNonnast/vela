"""Quick test: connect to Vela MCP server and list tools."""
import asyncio
import sys

from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession


async def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/mcp"
    print(f"Connecting to {url}...")

    try:
        async with streamablehttp_client(url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                print("Session initialized!")

                # List tools
                tools_result = await session.list_tools()
                print(f"\nTools ({len(tools_result.tools)}):")
                for tool in tools_result.tools:
                    print(f"  - {tool.name}")

                # List prompts
                prompts_result = await session.list_prompts()
                print(f"\nPrompts ({len(prompts_result.prompts)}):")
                for prompt in prompts_result.prompts:
                    print(f"  - {prompt.name}")

    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())

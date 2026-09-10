"""Exercise the actual MCP stdio adapter against a running local broker."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    root = Path(".airlock")
    tokens = json.loads((root / "keys/client-tokens.json").read_text())
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "airlock.cli", "mcp"],
        env={**os.environ, "AIRLOCK_AGENT_TOKEN": tokens["agent"]},
    )
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listing = await session.list_tools()
            assert [t.name for t in listing.tools] == ["request_context"]
            forbidden = await session.call_tool(
                "request_context",
                {"file_path": "../outside.airlock", "question": "Read it", "user_provenance": {}},
            )
            assert forbidden.isError
            assert any(
                "AIRLOCK_AGENT_WORKSPACE" in c.text for c in forbidden.content if c.type == "text"
            )
            result = await session.call_tool(
                "request_context",
                {
                    "file_path": "demo-workspace/employee_census.csv.airlock",
                    "question": "Which employees have birthdays in the next 14 dates including today?",
                    "user_provenance": {
                        "user_id": "mcp-demo",
                        "name": "Alex Morgan",
                        "roles": ["team_coordinator"],
                        "team": "engineering",
                        "purpose": "Birthday planning",
                    },
                },
            )
            text = "\n".join(c.text for c in result.content if c.type == "text")
            assert not result.isError
            assert "Maya Chen" in text and "Jordan Patel" in text and "000-00" not in text
            assert "applied_policy_ids" not in text
            print("MCP discovery and natural-language tool response verified.")
            print(text)


asyncio.run(main())

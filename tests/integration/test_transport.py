"""Read-only MCP registry/catalog verification; requires no running Live instance."""

import asyncio
import json
import os
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    environment = dict(os.environ, ABLETON_TOOLSETS="all")
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "enableton", "serve"], env=environment
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {tool.name: tool for tool in (await session.list_tools()).tools}
            assert len(tools) == 191, len(tools)
            for name in (
                "batch_commands",
                "undo",
                "create_native_bass",
                "get_audio_clip_timing",
                "modify_live_clip_notes",
                "apply_warp_repair",
            ):
                assert name in tools, name
            for name, arguments in (
                ("bass_design_catalog", {}),
                ("artist_bass_catalog", {}),
                ("mastering_recipe_catalog", {}),
                ("preview_bass_design", {"recipe": "riddim_square_fm"}),
                ("search_production_recipes", {}),
                ("describe_live_access", {}),
                ("describe_warp_workflow", {}),
            ):
                result = await session.call_tool(name, arguments)
                assert not result.isError, result
                data = json.loads(
                    next(content.text for content in result.content if hasattr(content, "text"))
                )
                if name == "bass_design_catalog":
                    assert len(data["recipes"]) == 13
                if name == "search_production_recipes":
                    assert data["total"] == 47
                print("Verified:", name)
            assert tools["apply_warp_repair"].annotations.destructiveHint
            assert tools["get_audio_clip_timing"].annotations.readOnlyHint
            print("191 tools verified; no Live mutations requested.")


if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(main(), 75))

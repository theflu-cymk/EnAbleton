"""Read-only MCP registry/catalog verification; requires no running Live instance."""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
import wave
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    environment = dict(os.environ, ABLETON_TOOLSETS="all")
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "enableton", "serve"], env=environment
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            result = await session.initialize()
            instructions = result.instructions or ""
            server_info = getattr(result, "serverInfo", None)
            server_instructions = getattr(server_info, "instructions", None) or ""
            assert server_instructions, "serverInfo.instructions missing"
            handshake = server_instructions
            assert "writes by default" in handshake, handshake
            for op_id in (
                "adopt",
                "name",
                "label",
                "voice",
                "level",
                "lock",
                "frame",
                "map",
                "check",
            ):
                assert op_id in handshake, op_id
            assert "writes by default" in (server_instructions or instructions)
            tools = {tool.name: tool for tool in (await session.list_tools()).tools}
            assert len(tools) == 242, len(tools)
            for name in (
                "batch_commands",
                "undo",
                "create_native_bass",
                "get_audio_clip_timing",
                "modify_live_clip_notes",
                "apply_warp_repair",
                "scan_audio_problems",
                "scan_clip_audio_problems",
                "plan_halftime_remix_workflow",
                "guide_halftime_remix_workflow",
                "refine_halftime_remix_workflow",
                "prepare_remix_session",
                "build_remix_session",
                "preview_remix_session",
                "compare_remix_previews",
                "inspect_remix_session",
                "plan_remix_midi_cleanup",
                "create_arrangement_audio_clip",
                "inspect_rack",
                "map_rack_blend_macro",
                "list_plugin_aliases",
                "resolve_plugin_parameter",
                "set_plugin_parameter",
                "guide_song_draft",
                "plan_song_draft",
                "refine_song_draft",
                "apply_song_draft",
                "describe_tool_families",
                "plan_track_preparation",
                "apply_track_preparation",
                "plan_instrument_assignment",
                "apply_instrument_assignment",
                "plan_audio_repair",
                "apply_audio_repair",
                "plan_track_alignment",
                "apply_track_alignment",
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
                ("guide_halftime_remix_workflow", {}),
                ("plan_halftime_remix_workflow", {"config": {}}),
                ("refine_halftime_remix_workflow", {"config": {}, "feedback": ["smoother"]}),
                ("describe_tool_families", {}),
                ("list_plugin_aliases", {}),
                ("guide_song_draft", {}),
                (
                    "plan_song_draft",
                    {"config": {"genre": "house", "energy": "medium", "key": "Am", "bars": 16}},
                ),
            ):
                result = await session.call_tool(name, arguments)
                assert not result.isError, result
                data = json.loads(
                    next(content.text for content in result.content if hasattr(content, "text"))
                )
                if name == "bass_design_catalog":
                    assert len(data["recipes"]) == 13
                if name == "search_production_recipes":
                    assert data["total"] == 50
                if name == "describe_tool_families":
                    assert data["live_changes"] is False
                    assert any(
                        tool == "map_rack_blend_macro"
                        for family in data["families"]
                        for tool in family["tools"]
                    )
                if name == "list_plugin_aliases":
                    assert data["profiles"][0]["name"] == "Serum"
                if name == "guide_song_draft":
                    assert data["live_changes"] is False and len(data["questions"]) <= 3
                if name == "plan_song_draft":
                    assert data["status"] == "planned" and data["playback_started"] is False
                print("Verified:", name)
            with tempfile.TemporaryDirectory() as temp:
                source = Path(temp) / "scan-fixture.wav"
                with wave.open(str(source), "wb") as audio:
                    audio.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
                    audio.writeframes(bytes(1600))
                result = await session.call_tool("scan_audio_problems", {"path": str(source)})
                assert not result.isError, result
                report = json.loads(next(c.text for c in result.content if hasattr(c, "text")))
                assert report["finding_counts"] == {}, report
                assert report["coverage"]["frames_analyzed"] == 800
                print("Verified: scan_audio_problems through MCP worker")
                # Exercise the local-files session-tool boundary without touching Live.
                from array import array
                import math

                with wave.open(str(source), "wb") as audio:
                    audio.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
                    audio.writeframes(
                        array(
                            "h",
                            [
                                round(8000 * math.sin(2 * math.pi * 220 * i / 8000))
                                for i in range(24000)
                            ],
                        ).tobytes()
                    )
                from enableton.remix_assets import project

                directory = str(Path(temp) / "remix-project")
                project(directory, True)
                result = await session.call_tool(
                    "compare_remix_previews",
                    dict(project_dir=directory, reference=str(source), variant=str(source)),
                )
                assert not result.isError, result
                report = json.loads(next(c.text for c in result.content if hasattr(c, "text")))
                assert (
                    Path(report["reference"]["path"]).exists()
                    and Path(report["variant"]["path"]).exists()
                ), report
                print("Verified: compare_remix_previews through MCP worker")
            for name in (
                "guide_halftime_remix_workflow",
                "plan_halftime_remix_workflow",
                "refine_halftime_remix_workflow",
            ):
                assert tools[name].annotations.readOnlyHint
            assert tools["plan_remix_midi_cleanup"].annotations.readOnlyHint
            assert tools["plan_instrument_assignment"].annotations.readOnlyHint
            assert tools["plan_audio_repair"].annotations.readOnlyHint
            assert tools["plan_track_alignment"].annotations.readOnlyHint
            assert tools["apply_instrument_assignment"].annotations.destructiveHint
            assert tools["apply_audio_repair"].annotations.destructiveHint
            assert tools["apply_track_alignment"].annotations.destructiveHint
            assert not tools["prepare_remix_session"].annotations.readOnlyHint
            assert tools["build_remix_session"].annotations.destructiveHint
            assert tools["preview_remix_session"].annotations.destructiveHint
            assert tools["scan_audio_problems"].annotations.readOnlyHint
            assert tools["scan_clip_audio_problems"].annotations.readOnlyHint
            assert tools["apply_warp_repair"].annotations.destructiveHint
            assert tools["get_audio_clip_timing"].annotations.readOnlyHint
            for name in (
                "guide_song_draft",
                "plan_song_draft",
                "refine_song_draft",
                "resolve_plugin_parameter",
                "list_plugin_aliases",
                "inspect_rack",
                "describe_tool_families",
            ):
                assert tools[name].annotations.readOnlyHint
            for name in (
                "apply_song_draft",
                "create_arrangement_audio_clip",
                "map_rack_blend_macro",
                "set_plugin_parameter",
            ):
                assert not tools[name].annotations.readOnlyHint
                assert tools[name].annotations.destructiveHint
            print("242 tools verified; no Live mutations requested.")


if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(main(), 75))

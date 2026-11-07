"""Generate the complete MCP catalog from the actual registered tool schemas."""

import asyncio
import json
import os
from pathlib import Path

os.environ["ABLETON_TOOLSETS"] = "all"
from enableton.server import mcp
from enableton import __version__


async def main():
    root = Path(__file__).resolve().parents[1]
    tools = await mcp.list_tools()
    rows = []
    for tool in sorted(tools, key=lambda tool: tool.name):
        registered = mcp._tool_manager.get_tool(tool.name)
        module = registered.fn.__module__
        row = tool.model_dump(mode="json", exclude_none=True)
        row["origin"] = "EnAbleton" if module.startswith("enableton") else "upstream"
        row["module"] = module
        rows.append(row)
    assert len(rows) == 202
    assert sum(row["origin"] == "EnAbleton" for row in rows) == 46
    document = {
        "enableton_version": __version__,
        "upstream_version": "1.8.1",
        "tool_count": len(rows),
        "tools": rows,
    }
    (root / "docs" / "tool-catalog.json").write_text(
        json.dumps(document, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# MCP tool catalog",
        "",
        f"Generated from EnAbleton {__version__}: 202 tools (156 upstream, 46 additions).",
        "",
        "Annotations describe intended effects; always inspect targets before edits.",
        "",
    ]
    for origin in ("EnAbleton", "upstream"):
        lines += ["## " + origin, "", "| Tool | Intent | Description |", "| --- | --- | --- |"]
        for row in rows:
            if row["origin"] != origin:
                continue
            annotation = row.get("annotations", {})
            intent = "Read-only" if annotation.get("readOnlyHint") else "Write / inspect before use"
            description = " ".join(row.get("description", "").split()).replace("|", "/")
            lines.append(f"| `{row['name']}` | {intent} | {description} |")
        lines.append("")
    (root / "docs" / "TOOL_CATALOG.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Generated 202-tool catalog, including 46 additions.")


if __name__ == "__main__":
    asyncio.run(main())

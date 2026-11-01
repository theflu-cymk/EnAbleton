"""EnAbleton stdio MCP application. Launch through `enableton serve`."""

from typing import Optional
import json
from pathlib import Path
from ableton_live_mcp import tools  # registers the upstream tools
from ableton_live_mcp.app import mcp
from ableton_live_mcp.connection import AbletonConnection, get_ableton_connection
from .bass_tools import register
from .bridge_version import COMPATIBLE_VERSIONS, UPSTREAM_VERSION


# Every upstream Live call must reject an old bridge: note-writing semantics
# differ between implementations. Catalog and offline tools remain usable.
_upstream_send = AbletonConnection.send_command


def _version_checked_send(self, command_type, params=None):
    if command_type != "get_script_info":
        info = _upstream_send(self, "get_script_info", {})
        if (
            info.get("version") not in COMPATIBLE_VERSIONS
            or info.get("upstream_version") != UPSTREAM_VERSION
        ):
            raise RuntimeError(
                "The new server is installed, but Live still has an older bridge loaded. Restart Live or reload the AbletonMCP Control Surface before making Live calls."
            )
    return _upstream_send(self, command_type, params)


AbletonConnection.send_command = _version_checked_send


def dispatch(command, args):
    connection = get_ableton_connection()
    info = connection.send_command("get_script_info", {})
    if info.get("upstream_version") != "1.8.1" or command not in info.get("capabilities", []):
        raise RuntimeError(
            "This bridge capability is not loaded. Save and fully restart Ableton Live, then retry; no command was sent."
        )
    return connection.send_command(command, args)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
def get_clip_envelope(
    track_index: int,
    clip_index: int,
    times: list[float],
    target: str = "device",
    device_index: int = 0,
    parameter_index: int = 0,
    send_index: int = 0,
    expected_track_name: Optional[str] = None,
    expected_clip_name: Optional[str] = None,
) -> dict:
    """Read sampled Session clip envelopes in native parameter units, with target guards."""
    return dispatch("get_clip_envelope", dict(locals()))


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
def write_clip_envelope(
    track_index: int,
    clip_index: int,
    points: list[dict[str, float]],
    target: str = "device",
    device_index: int = 0,
    parameter_index: int = 0,
    send_index: int = 0,
    interpolation: str = "linear",
    resolution: float = 0.0625,
    replace: bool = False,
    expected_track_name: Optional[str] = None,
    expected_clip_name: Optional[str] = None,
) -> dict:
    """Write verified, bounded Session envelopes. Read existing envelopes before replace=true.
    Native parameter values; times in clip beats. Linear curves approximate hold steps.
    Arrangement editing requires copying the Session clip back. One Live Undo step.
    """
    return dispatch("write_clip_envelope", dict(locals()))


register(mcp, dispatch)
from .access_tools import register_access

register_access(mcp, dispatch)
from .warp_tools import register_warp

register_warp(mcp, dispatch)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
def inspect_master_chain() -> dict:
    """Read Main/Master devices including nested rack chains, chain gain/mute,
    and each parameter's formatted value, enum options and automation state.
    Does not change processing or measure LUFS, true peak or gain reduction.
    Requires EXT.2 Live bridge; restart Live after installing the update.
    """
    return dispatch("inspect_master_chain", {})


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
def search_production_recipes(query: str = "") -> dict:
    """Search the full AbletonMCPEXT reference library: bass, layering, modulation,
    mastering, tutorials and artist methods. Read-only; reference entries are not
    executable presets. Sources and verification limits are preserved.
    """
    path = Path(__file__).with_name("production_recipes.json")
    if not path.exists():
        path = Path(__file__).parent.parent / "data" / "recipes.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data if isinstance(data, list) else data["entries"]
    words = query.casefold().split()
    matches = [
        r for r in entries if all(w in json.dumps(r, ensure_ascii=False).casefold() for w in words)
    ]
    return {"total": len(entries), "match_count": len(matches), "recipes": matches}


if __name__ == "__main__":
    mcp.run()

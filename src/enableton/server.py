"""EnAbleton stdio MCP application. Launch through `enableton serve`."""

from typing import Optional
import json
from pathlib import Path
from ableton_live_mcp import tools  # registers the upstream tools
from ableton_live_mcp.app import mcp
from ableton_live_mcp.connection import AbletonConnection, get_ableton_connection
import mcp.server.session as _mcp_session
import mcp.types as _mcp_types
from .bass_tools import register
from .bridge_version import COMPATIBLE_VERSIONS, UPSTREAM_VERSION
from .compat import require_supported
from .prep import instructions as prep_instructions
from .wire import install as install_wire

# FastMCP exposes instructions as a read-only property. The handshake reads
# the low-level server attribute, which is also InitializeResult.instructions.
# This SDK's serverInfo object does not receive that field unless we copy it.
_INSTRUCTIONS = prep_instructions()
mcp._mcp_server.instructions = _INSTRUCTIONS
_InitializeResult = _mcp_types.InitializeResult


def _initialize_result(*args, **kwargs):
    info = kwargs.get("serverInfo")
    text = kwargs.get("instructions") or _INSTRUCTIONS
    if text and info is not None and not getattr(info, "instructions", None):
        kwargs["serverInfo"] = info.model_copy(update={"instructions": text})
        kwargs["instructions"] = text
    return _InitializeResult(*args, **kwargs)


_mcp_session.types.InitializeResult = _initialize_result

# Frame the socket before this module replaces send_command. The wrapper below
# calls that framed sender; installing afterwards would skip the newline.
install_wire()

# Every upstream Live call must reject an old bridge: note-writing semantics
# differ between implementations. Catalog and offline tools remain usable.
_upstream_send = AbletonConnection.send_command

# The handshake is read once per connection. Reloading the control surface in
# Live tears the socket down, which fails the next send and clears this below,
# so a stale bridge is still refused. Only reads are cached, never a write.
_handshake = {"connection": None, "info": None}


def _forget_handshake():
    _handshake["connection"] = None
    _handshake["info"] = None


def _handshake_info(connection, refresh=False):
    if not refresh and _handshake["info"] is not None and _handshake["connection"] is connection:
        return _handshake["info"]
    info = _upstream_send(connection, "get_script_info", {})
    _handshake["connection"] = connection
    _handshake["info"] = info
    return info


def _require_version(info):
    if (
        info.get("version") not in COMPATIBLE_VERSIONS
        or info.get("upstream_version") != UPSTREAM_VERSION
    ):
        raise RuntimeError(
            "The new server is installed, but Live still has an older bridge loaded. Fully quit Live, select only EnAbleton, and set Input and Output to None before making Live calls."
        )
    # The documented Live floor. A bridge that predates the report field leaves
    # this unverified rather than refused; the installer ships a reporting one.
    require_supported(info.get("live_version"))


def _version_checked_send(self, command_type, params=None):
    try:
        if command_type == "get_script_info":
            return _handshake_info(self, refresh=True)
        _require_version(_handshake_info(self))
        return _upstream_send(self, command_type, params)
    except Exception:
        _forget_handshake()
        raise


AbletonConnection.send_command = _version_checked_send


def dispatch(command, args):
    connection = get_ableton_connection()
    # One capability/version check per connection; the wrapper's duplicate check
    # is bypassed only after validating the same conditions here.
    try:
        info = _handshake_info(connection)
        _require_version(info)
        if command not in info.get("capabilities", []):
            raise RuntimeError(
                "This bridge capability is not loaded. Save and fully restart Ableton Live, then retry; no command was sent."
            )
        return _upstream_send(connection, command, args)
    except Exception:
        _forget_handshake()
        raise


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
from .audio_scan_tools import register_audio_scan

register_audio_scan(mcp, dispatch)

from .remix_workflow import register_remix

register_remix(mcp)

from .remix_tools import register_remix_session

register_remix_session(mcp, dispatch)

from .remix_midi import register_midi_cleanup

register_midi_cleanup(mcp, dispatch)
from .groove_tools import register_groove

register_groove(mcp)
from .extended_tools import register_extended

register_extended(mcp, dispatch)
from .plugin_aliases import register_plugin_aliases

register_plugin_aliases(mcp, dispatch)
from .song_draft import register_song_draft

register_song_draft(mcp, dispatch)
from .track_prep import register_track_prep

register_track_prep(mcp, dispatch)
from .assign_instruments import register_instruments

register_instruments(mcp, dispatch)
from .audio_repair import register_audio_repair

register_audio_repair(mcp, dispatch)
from .align_tracks import register_track_alignment

register_track_alignment(mcp, dispatch)


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

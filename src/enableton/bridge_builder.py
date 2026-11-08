"""Generate the extended Remote Script from the installed, pinned upstream package.

Writes only the requested staging directory. Deployment and backups are separate.
"""

from importlib import resources
from pathlib import Path
import hashlib
import json
import shutil
import sys
import ableton_live_mcp
from .bridge_version import VERSION, UPSTREAM_VERSION
from . import __version__


def build(destination):
    if ableton_live_mcp.__version__ != UPSTREAM_VERSION:
        raise RuntimeError("This adapter requires exactly mcp-server-ableton-live==1.8.1")
    upstream = (
        resources.files("ableton_live_mcp")
        .joinpath("remote_script", "__init__.py")
        .read_text(encoding="utf-8")
    )
    source = upstream
    anchor = "from _Framework.ControlSurface import ControlSurface"
    if source.count(anchor) != 1:
        raise RuntimeError("Upstream 1.8.1 source changed: ControlSurface anchor is not unique")
    source = source.replace(
        anchor,
        anchor
        + "\nfrom .envelope_support import EnvelopeSupportMixin\nfrom .sound_design_support import SoundDesignSupportMixin\nfrom .access_support import AccessSupportMixin\nfrom .warp_support import WarpSupportMixin",
    )
    source = source.replace(
        "class AbletonMCP(ControlSurface):",
        "class AbletonMCP(WarpSupportMixin, AccessSupportMixin, SoundDesignSupportMixin, EnvelopeSupportMixin, ControlSurface):",
    )
    anchor = "    _ALL_COMMANDS = {**_MUTATING_COMMANDS, **_READONLY_COMMANDS}"
    if source.count(anchor) != 1:
        raise RuntimeError("Upstream 1.8.1 source changed: _ALL_COMMANDS anchor is not unique")
    extension = """
    # EXT compatibility commands retain guarded parameter batches and bounded envelopes.
    _READONLY_COMMANDS = dict(_READONLY_COMMANDS, **{
        "get_script_info": lambda s, p: {
            "version": "__EXT_VERSION__", "upstream_version": BRIDGE_VERSION,
            "enableton_version": "__DIST_VERSION__", "name": "EnAbleton",
            "capabilities": list(s._ALL_COMMANDS),
        },
        "get_sound_design_parameters": lambda s, p: s._get_sound_design_parameters(p),
        "get_clip_envelope": lambda s, p: s._get_clip_envelope(p),
        "inspect_master_chain": lambda s, p: s._inspect_master_chain(p),
        "inspect_device_tree": lambda s, p: s._inspect_master_chain(p),
        "read_access_object": lambda s, p: s._read_access_object(p),
        "get_access_mixer": lambda s, p: s._get_access_mixer(p),
        "get_access_notes": lambda s, p: s._get_access_notes(p),
        "get_audio_clip_timing": lambda s, p: s._get_audio_clip_timing(p),
    })
    _MUTATING_COMMANDS = dict(_MUTATING_COMMANDS, **{
        "set_sound_design_parameters": lambda s, p: s._set_sound_design_parameters(p),
        "write_clip_envelope": lambda s, p: s._write_clip_envelope(p),
        "write_access_object": lambda s, p: s._write_access_object(p),
        "set_access_mixer": lambda s, p: s._set_access_mixer(p),
        "modify_access_notes": lambda s, p: s._modify_access_notes(p),
        "repair_warp_duplicate": lambda s, p: s._repair_warp_duplicate(p),
        "insert_access_notes": lambda s, p: s._insert_access_notes(p),
        "delete_access_notes": lambda s, p: s._delete_access_notes(p),
        "set_access_warp": lambda s, p: s._set_access_warp(p),
    })
"""
    source = source.replace(
        anchor,
        extension.replace("__EXT_VERSION__", VERSION).replace("__DIST_VERSION__", __version__)
        + "\n"
        + anchor,
    )
    compile(source, "AbletonMCP/__init__.py", "exec")
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "__init__.py").write_bytes(source.encode("utf-8"))
    for name in (
        "envelope_support.py",
        "sound_design_support.py",
        "access_support.py",
        "warp_support.py",
        "warp_analysis.py",
        "numbers.py",
    ):
        shutil.copy2(Path(__file__).parent / name, destination / name)
    manifest = {
        "enableton_version": __version__,
        "upstream_version": UPSTREAM_VERSION,
        "extension_version": VERSION,
        "upstream_sha256": hashlib.sha256(upstream.encode()).hexdigest(),
        "generated_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "files": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.glob("*.py")
        },
    }
    (destination / "ext-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(json.dumps(build(sys.argv[1]), indent=2))

"""Default initial track preparation ("initiate the current track").

Entry point: when a run starts, ask whether to PREPARE or LINT the song.

- ``lint``    reads the running set and reports; it never writes.
- ``prepare`` lints first, then applies the enabled steps below in order.

Phases follow the nine preparation operations:

1 protect   a muted ORIGINAL copy
2 identify  track and clip names
3 audible   placeholder instruments, clip gain and DC
4 time      warp mode and bar lengths
5 navigate  section locators
6 gate      read-only lint

Song-folder creation is not one of these steps. It stays off unless
``enableton prep workspace`` is called. Add a step by appending to ``STEPS``.
"""

from copy import deepcopy
from pathlib import Path

import yaml

__all__ = [
    "ENTRY_QUESTION",
    "LINT",
    "MODES",
    "PHASES",
    "STEPS",
    "build_config",
    "describe",
    "write_config",
]

PHASES = ("protect", "identify", "audible", "time", "navigate", "gate")

MODES = ("lint", "prepare")

ENTRY_QUESTION = (
    "Prepare or lint the current song? Lint is read-only. Prepare lints first, "
    "then applies the enabled initial-preparation steps."
)


def _steps():
    from .prep import OPS

    notes = {
        "adopt": "Muted ORIGINAL copy. The working track name, notes, Warp and faders stay.",
        "name": "NN Label and a role colour. An ambiguous role is left unchanged.",
        "label": "Clip names use the owning track number, role, content and length.",
        "voice": "Stock placeholder on a MIDI track that has notes and no instrument.",
        "level": "Unity clip gain and Utility DC only. Level jumps are not dynamics.",
        "lock": "Warp mode from a reference. Markers and clip starts stay.",
        "frame": "Bar-align loop bounds. Seconds when unwarped, beats when warped.",
        "map": "Named section locators. An existing locator is not moved.",
        "check": "Lint findings. This step writes nothing.",
    }
    return [
        {
            "id": op["id"],
            "phase": op["phase"],
            "process": f"prep_{op['id']}",
            "enabled": op["writes"],
            "params": {},
            "note": notes[op["id"]],
        }
        for op in OPS
    ]


STEPS = _steps()

LINT = {
    "failOn": "warning",
    "includeSession": False,
    "rules": {
        "track_naming": {"enabled": True},
        "clip_naming": {"enabled": True, "severity": "info"},
        "missing_samples": {"enabled": True},
        "midi_validity": {"enabled": True},
        "midi_overlaps": {"enabled": True, "params": {"monophonicRoles": ["bass"]}},
        "midi_grid": {
            "enabled": True,
            "severity": "info",
            "params": {"gridBeats": 0.25, "toleranceBeats": 0.04},
        },
        "midi_dynamics": {"enabled": True},
        "harmonic_layering": {
            "enabled": True,
            "severity": "info",
            "params": {"minOverlapBeats": 0.5},
        },
        "empty_content": {"enabled": True, "severity": "info"},
        "clip_boundaries": {"enabled": True, "severity": "info"},
        "arrangement_overlaps": {"enabled": True},
        "warp_maps": {"enabled": True},
        "stem_sync": {"enabled": True, "params": {"groups": []}},
        "instrument_assignments": {"enabled": True},
        "track_colors": {"enabled": True, "severity": "info"},
        "session_settings": {"enabled": True},
        "organization": {"enabled": True, "severity": "info"},
    },
}


def _validate_preset():
    """Fail fast on a malformed step list; never silently drop a step."""

    seen = set()
    for step in STEPS:
        step_id = step.get("id")
        if not isinstance(step_id, str) or not step_id:
            raise ValueError("every step needs a non-empty id")
        if step_id in seen:
            raise ValueError(f"duplicate step id: {step_id}")
        seen.add(step_id)
        if step.get("phase") not in PHASES:
            raise ValueError(f"step {step_id}: phase must be one of {PHASES}")
        if not isinstance(step.get("process"), str) or not step["process"]:
            raise ValueError(f"step {step_id}: process must be a registered name")
        if type(step.get("enabled")) is not bool:
            raise ValueError(f"step {step_id}: enabled must be a boolean")
        if not isinstance(step.get("params"), dict):
            raise ValueError(f"step {step_id}: params must be an object")
        if set(step.get("target", {})) - {"trackIds", "clipIds", "types"}:
            raise ValueError(f"step {step_id}: unknown target selector")


def describe():
    """Read-out of the preset, in phase order, for docs and the CLI."""

    _validate_preset()
    return [
        {
            "phase": step["phase"],
            "id": step["id"],
            "process": step["process"],
            "enabled": step["enabled"],
            "note": step["note"],
        }
        for step in sorted(STEPS, key=lambda item: PHASES.index(item["phase"]))
    ]


def build_config(song_root, song_name, mode="lint", folder_name=None):
    """Ready-to-run YAML config; ``lint`` disables every write step."""

    if mode not in MODES:
        raise ValueError("mode must be lint or prepare")
    if not isinstance(song_root, str) or not song_root.strip():
        raise ValueError("song_root must be a non-empty path string")
    if not isinstance(song_name, str) or not song_name.strip():
        raise ValueError("song_name must be non-empty")
    _validate_preset()
    song = {"name": song_name.strip(), "root": song_root.strip(), "onExists": "reuse"}
    if folder_name:
        song["folderName"] = folder_name
    steps = []
    for step in STEPS:
        entry = {key: value for key, value in step.items() if key not in {"phase", "note"}}
        if mode == "lint":
            entry["enabled"] = False
        steps.append(deepcopy(entry))
    return {
        "schemaVersion": 1,
        "song": song,
        "lint": deepcopy(LINT),
        "defaults": {"processes": {}},
        "steps": steps,
    }


def write_config(path, song_root, song_name, mode="lint", folder_name=None):
    """Create the preset as YAML; an existing file is never replaced."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = yaml.safe_dump(build_config(song_root, song_name, mode, folder_name), sort_keys=False)
    with destination.open("x", encoding="utf-8", newline="") as handle:
        handle.write(payload)
    return destination

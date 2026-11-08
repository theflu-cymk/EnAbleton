"""Default initial track preparation ("initiate the current track").

Entry point: when a run starts, ask whether to PREPARE or LINT the song.

- ``lint``    reads the running set and reports; it never writes.
- ``prepare`` lints first, then applies the enabled steps below in order.

Phases mirror the documented run-down:

1 protect  inventory the set and create the song folder; originals are never targeted
2 audit    read-only rules for media, routing, arrangement, MIDI and audio
3 align    render-first Warp removal against a reference layer
4 name     ``NN Label`` names plus a role colour per layer
5 verify   report-only length/overlap/group checks, then re-lint

Add a step by appending to ``STEPS``; nothing else needs to change.
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

PHASES = ("protect", "audit", "align", "name", "verify")

MODES = ("lint", "prepare")

ENTRY_QUESTION = (
    "Prepare or lint the current song? Lint is read-only. Prepare lints first, "
    "then applies the enabled initial-preparation steps."
)

STEPS = [
    {
        "id": "workspace",
        "phase": "protect",
        "process": "create_song_folder",
        "enabled": True,
        "params": {},
        "note": "Creates the song folder only; the Live set is untouched.",
    },
    {
        "id": "inventory",
        "phase": "protect",
        "process": "cleanup_unused",
        "enabled": True,
        "params": {"collect": False, "save": False},
        "note": "Read-only inventory; never deletes user files.",
    },
    {
        "id": "missing-media",
        "phase": "audit",
        "process": "check_missing_samples",
        "enabled": True,
        "params": {},
        "note": "Missing or unresolved audio is reported, never relinked.",
    },
    {
        "id": "session-defaults",
        "phase": "audit",
        "process": "set_session_defaults",
        "enabled": False,
        "params": {"tempo": 120, "numerator": 4, "denominator": 4, "force": False},
        "note": "Off by default: keep the existing tempo and grid unless measured.",
    },
    {
        "id": "empty-clips",
        "phase": "audit",
        "process": "remove_empty_clips",
        "enabled": False,
        "params": {},
        "note": "Review the selection first; missing media is not empty.",
    },
    {
        "id": "empty-tracks",
        "phase": "audit",
        "process": "remove_empty_tracks",
        "enabled": False,
        "params": {},
        "note": "Groups, returns, master, inputs and automation stay protected.",
    },
    {
        "id": "note-overlaps",
        "phase": "audit",
        "process": "fix_midi_overlaps",
        "enabled": False,
        "params": {},
        "target": {"types": ["midi"]},
        "note": "Same-pitch overlaps only, and only after the lint review.",
    },
    {
        "id": "midi-grid",
        "phase": "audit",
        "process": "quantize_timing",
        "enabled": False,
        "params": {},
        "target": {"types": ["midi"]},
        "note": "Swing, pickups and fast fills are intentional; opt in per part.",
    },
    {
        "id": "velocities",
        "phase": "audit",
        "process": "normalize_velocities",
        "enabled": False,
        "params": {"mode": "clamp", "min": 40, "max": 112},
        "target": {"types": ["midi"]},
        "note": "Off by default; accents are content, not noise.",
    },
    {
        "id": "lengths",
        "phase": "verify",
        "process": "fix_clip_lengths",
        "enabled": True,
        "params": {"mode": "report", "toleranceBeats": 0.04, "allowTrim": False},
        "note": "Report only; never forces equal lengths or trims real tails.",
    },
    {
        "id": "warp",
        "phase": "align",
        "process": "unwrap_layers",
        "enabled": False,
        "params": {"reference": None, "renders": {}},
        "note": "Needs a reference; renders are bounced at project tempo first.",
    },
    {
        "id": "layers",
        "phase": "name",
        "process": "apply_layer_naming",
        "enabled": True,
        "params": {},
        "note": "NN Label names and one colour per role; empty tracks skipped.",
    },
    {
        "id": "grouping",
        "phase": "verify",
        "process": "organize_groups",
        "enabled": True,
        "params": {"apply": False},
        "note": "Report only: Live exposes no group-creation API.",
    },
    {
        "id": "arrangement-overlaps",
        "phase": "verify",
        "process": "trim_overlapping_clips",
        "enabled": True,
        "params": {"apply": False},
        "note": "Destructive trimming needs a guarded duplicate workflow.",
    },
]

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

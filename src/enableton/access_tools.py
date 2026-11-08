"""Typed entrypoints over the constrained EnAbleton target schema."""

from .bridge_version import VERSION

TARGET_HELP = """Target schema: track_type=track|return|master, track_index (0-based),
expected_track_name. Nested devices: device_path=[device,chain,device,...],
expected_device_name. Chain: device_path points to its rack; chain_index,
expected_chain_name. Clip: clip_view=session|arrangement, clip_index,
expected_clip_name; Arrangement writes also require expected_start_time in beats.
Never guess paths: inspect_live_device_tree and read the current object first."""


def register_access(mcp, dispatch):
    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def get_audio_clip_timing(target: dict) -> dict:
        """Read every audio warp marker, source path, clip/loop/start markers,
        pitch and Arrangement boundaries. Target: track_index, clip_index,
        clip_view=session|arrangement and optional name/start guards. Source marker
        sample_time is seconds; beat_time is clip beats. Requires EXT.4 bridge.
        Does not validate audible transients or modify audio/markers.
        """
        return dispatch("get_audio_clip_timing", target)

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def describe_live_access() -> dict:
        """Describe executable coverage and limits, without implying complete UI access."""
        return {
            "version": VERSION,
            "target_schema": TARGET_HELP,
            "added": [
                "Nested device trees and guarded parameter batches on tracks/returns/Main",
                "Track and rack-chain mixer gain/pan/sends",
                "Explicit song/track/scene/clip/chain scalar properties",
                "Full-range Session and Arrangement MIDI reads, note-ID edits, and verified insert/delete",
            ],
            "upstream": [
                "transport/recording",
                "routing",
                "device loading",
                "track/clip creation and deletion",
                "Session automation",
                "browser",
                "scenes",
                "rack macros",
                "drum pads",
                "offline ALS inspection",
            ],
            "limits": [
                "Not every Ableton UI function is in the Live API",
                "Third-party plug-in controls must be exposed by Live; hidden plug-in internals are unavailable",
                "No arbitrary Python execution or unrestricted object-property setter",
                "No track reordering API or direct Arrangement automation added here",
                "Preferences, plug-in windows, audio-to-MIDI conversion and GUI-only commands remain manual",
                "Values use native API units; inspect formatted values before writing",
                "Software tests are not proof of runtime support; verify actual Live readbacks",
            ],
        }

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def inspect_live_device_tree(track_type: str = "track", track_index: int = 0) -> dict:
        """Read every nested device, chain, parameter and formatted value on a track,
        return or Main. track_type=track|return|master. Bounded to 256 devices/depth 8.
        """
        return dispatch("inspect_device_tree", dict(track_type=track_type, track_index=track_index))

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def get_nested_device_parameters(target: dict) -> dict:
        """Read nested parameters. Target: track_type, track_index, device_path
        [device,chain,device,...], optional expected_track_name/expected_device_name.
        Main uses track_type=master. Values are native with formatted units.
        """
        return dispatch("get_sound_design_parameters", target)

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
    def set_nested_device_parameters(target: dict, parameters: dict[str, float]) -> dict:
        """Guarded, verified nested parameter batch on track/return/Main. Read first.
        Target requires expected_track_name, expected_device_name and device_path.
        Native values only; refuses automated controls. Rollback and one Undo step.
        """
        if not target.get("expected_track_name") or not target.get("expected_device_name"):
            raise ValueError("Track and device name guards are required")
        return dispatch("set_sound_design_parameters", dict(target, parameters=parameters))

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def read_live_object(target: dict) -> dict:
        """Read scalar properties and availability. object_type=song|track|scene|clip|chain.
        Clip target: track_type, track_index, clip_view=session|arrangement, clip_index.
        Scene uses scene_index. Chain uses device_path to rack and chain_index.
        """
        return dispatch("read_access_object", target)

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
    def write_live_object(target: dict, properties: dict) -> dict:
        """Write exposed song/track/scene/clip/chain properties after read_live_object.
        Only documented allowlisted fields; native units. Name guards required for
        track/clip/chain; Arrangement writes require expected_start_time. Validated
        whole batch, readback, rollback and one Undo. No arbitrary property access.
        """
        _arrangement_guard(target)
        return dispatch("write_access_object", dict(target, properties=properties))

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def get_live_mixer(target: dict) -> dict:
        """Read track/return/Main or nested chain volume, pan and sends. Chain target
        adds device_path to its rack plus chain_index. Values include formatted units.
        """
        return dispatch("get_access_mixer", target)

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
    def set_live_mixer(target: dict, parameters: dict[str, float]) -> dict:
        """Set track/return/Main or rack-chain mixer: volume, pan, send:N. Native
        values, not assumed dB. Read mixer first. Track and chain name guards,
        automated-control refusal, verified readback, rollback and one Undo step.
        """
        return dispatch("set_access_mixer", dict(target, parameters=parameters))

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def get_live_clip_notes(target: dict) -> dict:
        """Read ALL MIDI notes including note IDs from Session or Arrangement,
        including notes outside offset loop bounds. No partial-read fallback.
        Target: track_index, clip_view=session|arrangement, clip_index and names.
        """
        return dispatch("get_access_notes", target)

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
    def modify_live_clip_notes(target: dict, notes: list[dict]) -> dict:
        """Modify existing notes by note_id in Session or Arrangement without
        recreating the clip. Each entry needs note_id plus pitch/start_time/duration/
        velocity/mute/probability/deviation/release fields to change. Read all notes
        first; names and Arrangement start guard required. Live reassigns the ID of
        each edited note because the edit removes and re-adds it; other notes keep
        their IDs and expression data. Does not add unrelated notes or rewrite MPE
        expression curves. One Undo step.
        """
        _arrangement_guard(target)
        return dispatch("modify_access_notes", dict(target, notes=notes))

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
    def insert_live_clip_notes(target: dict, notes: list[dict]) -> dict:
        """Insert new notes into a MIDI clip without replacing existing content.
        Each note needs pitch, start_time and duration; velocity defaults to 100.
        Optional mute/probability/velocity_deviation/release_velocity are validated.
        Name and Arrangement start guards required. Verified by readback; one Undo
        step. Does not create MPE expression curves.
        """
        _arrangement_guard(target)
        return dispatch("insert_access_notes", dict(target, notes=notes))

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
    def delete_live_clip_notes(target: dict, notes: list[dict]) -> dict:
        """Delete existing notes by note_id from a Session or Arrangement MIDI clip.
        Untouched notes keep their identity and expression data. Identical pitch and
        start-time pairs are refused before any write because Live addresses notes by
        window, not by ID. Verified by readback; one Undo step.
        """
        _arrangement_guard(target)
        return dispatch("delete_access_notes", dict(target, notes=notes))


def _arrangement_guard(target):
    if target.get("clip_view") == "arrangement" and target.get("expected_start_time") is None:
        raise ValueError("Arrangement writes require expected_start_time")

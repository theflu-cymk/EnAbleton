"""Tools closing the remaining upstream gaps: devices, chains, cues, scenes, analysis."""

from . import energy as energy_lib
from .numbers import finite
from .replicate_audio import analyze_song_structure as structure_via_replicate
from .replicate_audio import describe_audio


def register_extended(mcp, dispatch):
    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
    def set_eq_bands(
        track_index: int,
        device_index: int,
        bands: list[dict],
        mode: str = "A",
        expected_device_name: str | None = None,
    ) -> dict:
        """Set several EQ Eight bands in one call on the clip's or track's EQ Eight.
        bands entries take band 1..8 plus any of filter_on, frequency_hz, gain_db, q.
        Frequencies and gains are reached through the parameter's own display string,
        not a guessed log formula, and every written band is read back. mode is A or B.
        Bands with no field are refused. One Live Undo step. Needs the EXT.12 bridge.
        """
        return dispatch(
            "set_eq_bands",
            {
                "track_index": track_index,
                "device_index": device_index,
                "bands": bands,
                "mode": mode,
                "expected_device_name": expected_device_name,
            },
        )

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
    def insert_chain(
        track_index: int,
        device_index: int,
        chain_index: int | None = None,
        expected_device_name: str | None = None,
    ) -> dict:
        """Add one chain to an Instrument/Effect Rack and verify the chain count grew by
        exactly one. Refuses when this Live build does not expose RackDevice.insert_chain.
        One Live Undo step. Needs the EXT.12 bridge.
        """
        params = {
            "track_index": track_index,
            "device_index": device_index,
            "expected_device_name": expected_device_name,
        }
        if chain_index is not None:
            params["chain_index"] = chain_index
        return dispatch("insert_chain", params)

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
    def delete_chain(
        track_index: int,
        device_index: int,
        chain_index: int,
        expected_chain_name: str | None = None,
    ) -> dict:
        """Remove one chain from a rack, refusing the last remaining chain and any name
        mismatch, then verify the count shrank by exactly one. One Live Undo step.
        Needs the EXT.12 bridge.
        """
        return dispatch(
            "delete_chain",
            {
                "track_index": track_index,
                "device_index": device_index,
                "chain_index": chain_index,
                "expected_chain_name": expected_chain_name,
            },
        )

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
    def insert_device_to_chain(
        track_index: int, device_index: int, chain_index: int, device_name: str
    ) -> dict:
        """Insert one native device into a rack chain by browser name and verify the device
        count grew by one. Third-party and Max devices are not covered. Refuses when this
        Live build does not expose Chain.insert_device. One Live Undo step. EXT.12 bridge.
        """
        return dispatch(
            "insert_device_to_chain",
            {
                "track_index": track_index,
                "device_index": device_index,
                "chain_index": chain_index,
                "device_name": device_name,
            },
        )

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
    def delete_cue_point(time: float) -> dict:
        """Delete the single Arrangement locator at that beat position and verify the count
        dropped by one. Live has no direct cue delete, so this moves the playhead to the cue,
        toggles the cue there and restores the previous playhead. Refuses when no cue sits at
        that time or when several do. Needs the EXT.12 bridge.
        """
        session = dispatch("get_session_info", {})
        previous = session.get("current_song_time")
        dispatch("set_current_song_time", {"time": time})
        try:
            report = dispatch("delete_cue_point", {"time": time})
        finally:
            if isinstance(previous, (int, float)):
                dispatch("set_current_song_time", {"time": previous})
        return report

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def get_scenes() -> dict:
        """List every scene with its index, name, colour, tempo and how many tracks hold a
        clip in it. Read-only. Needs the EXT.12 bridge.
        """
        return dispatch("get_scenes", {})

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def analyze_energy(
        path: str, bpm: float = 120.0, start_seconds: float = 0, max_seconds: float = 30
    ) -> dict:
        """Measure RMS, flux and five band envelopes per sixteenth note in a bounded local
        PCM WAV window, each normalized 0..1. The band split is a one-pole cascade, so treat
        the bands as relative movement, not calibrated spectrum or LUFS. Unsupported formats
        fail explicitly. No Live access or changes.
        """
        return energy_lib.energy_series(path, bpm, start_seconds, max_seconds)

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def analyze_frequency_clash(
        file_a: str,
        file_b: str,
        bpm: float = 120.0,
        start_seconds: float = 0,
        max_seconds: float = 30,
        top: int = 5,
    ) -> dict:
        """Compare two local PCM WAV files band by band and rank where their energy
        overlaps, with EQ Eight band numbers and a starting cut suggestion. Overlap is not
        automatically a problem: level and arrangement decide, so audition first. Read-only.
        """
        return energy_lib.band_clash(file_a, file_b, bpm, start_seconds, max_seconds, top)

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
    def annotate_arrangement(
        path: str,
        bpm: float | None = None,
        max_seconds: float = 120,
        min_segment_sixteenths: int = 32,
        threshold: float = 0.12,
        prefix: str = "Section",
    ) -> dict:
        """Create Arrangement locators at measured level changes in a local PCM WAV, named
        prefix + index + energy class. Refuses while the transport plays. Boundaries are level
        changes, not confirmed song sections: listen before trusting a split.
        """
        session = dispatch("get_session_info", {})
        if session.get("is_playing"):
            raise ValueError("Stop playback before annotating the Arrangement")
        tempo = finite(bpm if bpm is not None else session["tempo"], "bpm")
        window = max_seconds if max_seconds <= 120 else 120
        series = energy_lib.energy_series(path, tempo, 0, window)
        plan = energy_lib.segment_plan(series, min_segment_sixteenths, threshold)
        created = []
        for position, segment in enumerate(plan["segments"], start=1):
            beat = round(segment["start_seconds"] * tempo / 60.0, 4)
            name = "%s %d %s" % (prefix, position, segment["energy_class"])
            # create_locator acts at the playhead read by Live's main thread, so the
            # playhead must be moved by a separate command first or the cue lands late.
            dispatch("set_current_song_time", {"time": beat})
            created.append(dispatch("create_locator", {"name": name}))
        return {
            "segments": plan["segments"],
            "created": created,
            "count": len(created),
            "note": "Locators mark measured level changes, not confirmed song sections",
        }

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
    def create_structure_track(
        path: str,
        bpm: float | None = None,
        track_name: str = "Structure",
        max_seconds: float = 120,
        min_segment_sixteenths: int = 32,
        threshold: float = 0.12,
    ) -> dict:
        """Build a MIDI structure track whose notes mark measured energy sections of a local
        PCM WAV: pitch 84 high, 79 mid, 74 low, one note per section. Creates a new MIDI track
        and a Session clip, then leaves duplication into the Arrangement to you. Refuses while
        the transport plays. Energy classes are measured, not musical labels.
        """
        session = dispatch("get_session_info", {})
        if session.get("is_playing"):
            raise ValueError("Stop playback before building a structure track")
        tempo = finite(bpm if bpm is not None else session["tempo"], "bpm")
        window = max_seconds if max_seconds <= 120 else 120
        series = energy_lib.energy_series(path, tempo, 0, window)
        plan = energy_lib.segment_plan(series, min_segment_sixteenths, threshold)
        pitches = {"high": 84, "mid": 79, "low": 74}
        notes = []
        for segment in plan["segments"]:
            start = round(segment["start_seconds"] * tempo / 60.0, 4)
            length = segment["length_sixteenths"] * series["sixteenth_seconds"] * tempo / 60.0
            notes.append(
                {
                    "pitch": pitches[segment["energy_class"]],
                    "start_time": start,
                    "duration": round(max(0.25, length), 4),
                    "velocity": 100,
                    "mute": False,
                }
            )
        total = max(note["start_time"] + note["duration"] for note in notes)
        created = dispatch("create_midi_track", {"index": -1})
        track_index = created.get("track_index", created.get("index"))
        if not isinstance(track_index, int):
            raise RuntimeError("create_midi_track returned no track index; inspect Live")
        dispatch("set_track_name", {"track_index": track_index, "name": track_name})
        dispatch("create_clip", {"track_index": track_index, "clip_index": 0, "length": total})
        dispatch(
            "add_notes_to_clip",
            {"track_index": track_index, "clip_index": 0, "notes": notes},
        )
        return {
            "track_index": track_index,
            "track_name": track_name,
            "notes": len(notes),
            "length_beats": round(total, 3),
            "segments": plan["segments"],
            "next": "Duplicate this Session clip to Arrangement beat 0 with duplicate_to_arrangement",
            "limits": "Section boundaries are measured level changes, not confirmed song sections",
        }

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def analyze_song_structure(
        path: str,
        target_bpm: float | None = None,
        include_beats: bool = True,
        include_key: bool = True,
    ) -> dict:
        """Ask the pinned third-party All-In-One model on Replicate for BPM, key, labelled
        segments, beats and downbeats of a local audio file. Requires REPLICATE_API_TOKEN and
        uploads the file; nothing else in this package leaves the machine. target_bpm pins the
        tempo search. Third-party output: verify every boundary before editing. No Live access.
        """
        return structure_via_replicate(path, target_bpm, include_beats, include_key)

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def analyze_audio_describe(path: str, prompt: str, max_new_tokens: int = 512) -> dict:
        """Ask the pinned third-party Music Flamingo model on Replicate a question about a
        local audio file (harmony, structure, timbre, lyrics). Requires REPLICATE_API_TOKEN and
        uploads the file; nothing else in this package leaves the machine. A language-model
        description, not measurement: treat tempo, key and structure claims as unverified.
        """
        return describe_audio(path, prompt, max_new_tokens)

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
    def create_arrangement_audio_clip(
        track_index: int,
        path: str,
        position: float,
        expected_track_name: str,
    ) -> dict:
        """Import an audio file onto an audio track's Arrangement at a free beat.
        The path must already exist. Refuses a position inside an existing clip,
        and removes the import if its length overlaps another clip. Does not start
        playback. One Live Undo step. Needs the EXT.13 bridge. Session import
        remains create_audio_clip.
        """
        return dispatch(
            "create_arrangement_audio_clip",
            {
                "track_index": track_index,
                "path": path,
                "position": position,
                "expected_track_name": expected_track_name,
            },
        )

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def inspect_rack(
        track_index: int,
        device_index: int,
        expected_device_name: str | None = None,
    ) -> dict:
        """Read one rack's macro support and the Dry/Wet, Mix or Amount parameter on
        each chain device. Read-only. Needs the EXT.13 bridge. An empty chain list
        is reported, not treated as a failure.
        """
        return dispatch(
            "inspect_rack",
            {
                "track_index": track_index,
                "device_index": device_index,
                "expected_device_name": expected_device_name,
            },
        )

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
    def map_rack_blend_macro(
        track_index: int,
        device_index: int,
        expected_device_name: str,
        macro_index: int = 0,
        macro_name: str = "Blend",
    ) -> dict:
        """Map nested Dry/Wet, Mix or Amount parameters to one rack macro and name
        that macro Blend unless macro_name is set. macro_index is 0..7. Refuses
        when this Live build has no RackDevice.macro_map. Devices without a blend
        parameter are skipped. One Live Undo step. Needs the EXT.13 bridge.
        """
        return dispatch(
            "map_rack_blend_macro",
            {
                "track_index": track_index,
                "device_index": device_index,
                "expected_device_name": expected_device_name,
                "macro_index": macro_index,
                "macro_name": macro_name,
            },
        )

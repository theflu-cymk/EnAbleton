"""MCP orchestration for native bass synthesis and clip automation."""

import threading
import time
from typing import Optional
from .bass_recipes import RECIPES, SOURCES, get_recipe
from .bass_patterns import curve_points, phrase, inspect_sub_notes, finite
from .tutorial_layering import gun_blueprint
from .artist_methods import catalog as artist_catalog
from .mastering_recipes import catalog as mastering_catalog, plan as mastering_plan

_mutation_lock = threading.Lock()


def register(mcp, send):
    def require(*commands):
        info = send("get_script_info", {})
        missing = set(commands) - set(info.get("capabilities", []))
        if missing:
            raise RuntimeError(
                "Restart Ableton Live to load the bass/envelope bridge. Missing: "
                + ", ".join(sorted(missing))
            )

    def track_info(track_index, expected_track_name=None):
        if isinstance(track_index, bool) or not isinstance(track_index, int) or track_index < 0:
            raise ValueError("track_index must be nonnegative")
        track = send("get_track_info", {"track_index": track_index})
        if expected_track_name is not None and track["name"] != expected_track_name:
            raise ValueError("Track name changed; refresh track indexes")
        return track

    def session_clip(track, clip_index):
        if (
            isinstance(clip_index, bool)
            or not isinstance(clip_index, int)
            or not 0 <= clip_index < len(track["clip_slots"])
        ):
            raise ValueError("clip_index out of range")
        slot = track["clip_slots"][clip_index]
        if not slot["has_clip"]:
            raise ValueError(
                "Session clip slot is empty; Arrangement clips cannot be edited directly"
            )
        return slot["clip"]

    def resolve_device(spec):
        data = send("get_browser_items_at_path", {"path": spec["category"]})
        matches = [
            item for item in data["items"] if item["name"] == spec["name"] and item["is_loadable"]
        ]
        if len(matches) != 1:
            raise ValueError("Native device not available: " + spec["name"])
        if spec.get("preset"):
            data = send(
                "get_browser_items_at_path", {"path": spec["category"] + "/" + spec["name"]}
            )
            matches = [
                item
                for item in data["items"]
                if item["name"] == spec["preset"] and item["is_loadable"]
            ]
            if len(matches) != 1:
                raise ValueError("Native preset not available: " + spec["preset"])
        return matches[0]["uri"]

    def parameter(track_index, device_index, parameter_name, expected_track_name):
        data = send(
            "get_sound_design_parameters",
            {
                "track_index": track_index,
                "device_index": device_index,
                "expected_track_name": expected_track_name,
            },
        )
        matches = [p for p in data["parameters"] if p["name"] == parameter_name]
        if len(matches) != 1:
            raise ValueError("Missing or ambiguous parameter: " + parameter_name)
        if matches[0]["is_quantized"]:
            raise ValueError("Continuous bass movement requires a non-quantized parameter")
        return matches[0]

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def bass_design_catalog(style: str = "all", recipe: Optional[str] = None) -> dict:
        """Research-backed native bass methods for dubstep, brostep and tearout. Returns original recipes, chain settings, movement suggestions and primary-source links. No Live changes; not copies of artist presets."""
        if style not in ("all", "dubstep", "brostep", "tearout"):
            raise ValueError("Unknown style")
        recipes = (
            [get_recipe(recipe)]
            if recipe is not None
            else [
                get_recipe(k) for k, v in RECIPES.items() if style == "all" or v["style"] == style
            ]
        )
        return {
            "recipes": recipes,
            "sources": SOURCES,
            "artist_methods": {
                "catalog_tool": "artist_bass_catalog",
                "scope": "Documented artist principles versus original native adaptations",
            },
            "mastering": {
                "catalog_tool": "mastering_recipe_catalog",
                "plan_tool": "preview_mastering_plan",
                "scope": "Seven read-only mastering recipes with displayed-unit starting points and measurement gates",
            },
            "limits": "Recipe numbers are native API values and original starting points. Listen and refine; no audio-quality claim. Session envelopes require the extended Live bridge.",
        }

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def preview_bass_design(
        recipe: str = "tearout_fm",
        style: str = "tearout",
        bars: int = 4,
        root_midi: int = 29,
        role: str = "call",
        seed: int = 0,
    ) -> dict:
        """Preview exact native-device recipe and deterministic MIDI notes without touching Live. MIDI 29 is F0 in Live's octave naming; call is +12 semitones, response +24, sub stays at root."""
        return {"recipe": get_recipe(recipe), "phrase": phrase(style, bars, root_midi, role, seed)}

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def get_sound_design_parameters(
        track_index: int, device_index: int, expected_track_name: Optional[str] = None
    ) -> dict:
        """Inspect Live parameter names, raw ranges, displayed values and enum options. Raw 0..1 values may be nonlinear; do not assume Hz/dB/ms. Top-level devices only."""
        require("get_sound_design_parameters")
        return send(
            "get_sound_design_parameters",
            {
                "track_index": track_index,
                "device_index": device_index,
                "expected_track_name": expected_track_name,
            },
        )

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
    def set_sound_design_parameters(
        track_index: int,
        device_index: int,
        parameters: dict[str, float],
        expected_track_name: str,
        expected_device_name: Optional[str] = None,
    ) -> dict:
        """Set an exact-name parameter batch in native API units with validation, readback and rollback on failure. Refuses automated controls. One Live Undo step per batch. Integer coarse/fractional fine tuning must be separate controls. Use parameter inspection first."""
        with _mutation_lock:
            require("set_sound_design_parameters")
            return send(
                "set_sound_design_parameters",
                dict(
                    track_index=track_index,
                    device_index=device_index,
                    parameters=parameters,
                    expected_track_name=expected_track_name,
                    expected_device_name=expected_device_name,
                ),
            )

    def movement(
        track_index,
        clip_index,
        shape,
        device_index,
        parameter_name,
        low,
        high,
        cycle_beats,
        resolution,
        kick_times,
        release_beats,
        hold_beats,
        replace,
        expected_track_name,
    ):
        require("write_clip_envelope", "get_clip_envelope", "get_sound_design_parameters")
        low, high = finite(low, "low"), finite(high, "high")
        if not 0 <= low <= high <= 1:
            raise ValueError(
                "Movement low/high are normalized to the selected parameter's native min..max range"
            )
        track = track_info(track_index, expected_track_name)
        clip = session_clip(track, clip_index)
        target = "volume" if parameter_name == "track_volume" else "device"
        if target == "device":
            p = parameter(track_index, device_index, parameter_name, track["name"])
            parameter_index = p["index"]
        else:
            parameter_index = 0
        metadata = send(
            "get_clip_envelope",
            {
                "track_index": track_index,
                "clip_index": clip_index,
                "device_index": device_index,
                "parameter_index": parameter_index,
                "target": target,
                "times": [],
                "expected_track_name": track["name"],
                "expected_clip_name": clip["name"],
            },
        )
        start, end = metadata["loop_start"], metadata["loop_end"]
        native_low = metadata["min"] + low * (metadata["max"] - metadata["min"])
        native_high = metadata["min"] + high * (metadata["max"] - metadata["min"])
        points = curve_points(
            shape,
            start,
            end,
            native_low,
            native_high,
            cycle_beats,
            resolution,
            kick_times,
            release_beats,
            hold_beats,
        )
        result = send(
            "write_clip_envelope",
            {
                "track_index": track_index,
                "clip_index": clip_index,
                "device_index": device_index,
                "parameter_index": parameter_index,
                "target": target,
                "points": points,
                "interpolation": "hold",
                "resolution": resolution,
                "replace": replace,
                "expected_track_name": track["name"],
                "expected_clip_name": clip["name"],
            },
        )
        result["shape"] = shape
        result["gain_units_note"] = (
            "Track volume is Live's native mixer scale, not linear amplitude or dB"
            if target == "volume"
            else None
        )
        return result

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
    def apply_bass_movement(
        track_index: int,
        clip_index: int,
        expected_track_name: str,
        shape: str = "wobble",
        device_index: int = 0,
        parameter_name: str = "Filter Freq",
        low: float = 0.3,
        high: float = 0.75,
        cycle_beats: float = 1,
        resolution: float = 0.0625,
        kick_times: Optional[list[float]] = None,
        release_beats: float = 0.5,
        hold_beats: float = 0.0625,
        replace: bool = False,
    ) -> dict:
        """Write rhythmic wobble/growl/yoi/pluck/sweep/machinegun/duck automation to a Session clip, then verify readback. low/high normalized within native parameter range. parameter_name=track_volume controls mixer gain. Duck requires explicit kick_times in this clip's beat timeline; not audio-reactive sidechain. Existing target envelopes require replace=true. No Arrangement mutation."""
        with _mutation_lock:
            return movement(
                track_index,
                clip_index,
                shape,
                device_index,
                parameter_name,
                low,
                high,
                cycle_beats,
                resolution,
                kick_times,
                release_beats,
                hold_beats,
                replace,
                expected_track_name,
            )

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False})
    def create_bass_phrase(
        track_index: int,
        clip_index: int,
        expected_track_name: str,
        style: str = "tearout",
        bars: int = 4,
        root_midi: int = 29,
        role: str = "call",
        seed: int = 0,
    ) -> dict:
        """Create a deterministic call/response/sub MIDI phrase in an EMPTY Session slot. Styles tearout/tearout_triplet/brostep/dubstep/halftime. Does not replace notes, change tempo, launch playback, or edit Arrangement. Preview first with preview_bass_design."""
        material = phrase(style, bars, root_midi, role, seed)
        with _mutation_lock:
            track = track_info(track_index, expected_track_name)
            if not track["is_midi_track"]:
                raise ValueError("MIDI track required")
            if (
                isinstance(clip_index, bool)
                or not isinstance(clip_index, int)
                or not 0 <= clip_index < len(track["clip_slots"])
            ):
                raise ValueError("clip_index out of range")
            if track["clip_slots"][clip_index]["has_clip"]:
                raise ValueError("Clip slot occupied; existing content preserved")
            send(
                "create_clip",
                {
                    "track_index": track_index,
                    "clip_index": clip_index,
                    "length": material["length"],
                },
            )
            send(
                "set_clip_name",
                {
                    "track_index": track_index,
                    "clip_index": clip_index,
                    "name": style.upper() + " - " + role,
                },
            )
            send(
                "add_notes_to_clip",
                {"track_index": track_index, "clip_index": clip_index, "notes": material["notes"]},
            )
            actual = send("get_clip_notes", {"track_index": track_index, "clip_index": clip_index})
            expected = sorted(
                (n["pitch"], round(n["start_time"], 4), round(n["duration"], 4), n["velocity"])
                for n in material["notes"]
            )
            observed = sorted(
                (n["pitch"], round(n["start_time"], 4), round(n["duration"], 4), n["velocity"])
                for n in actual["notes"]
            )
            if expected != observed:
                raise RuntimeError("MIDI readback mismatch; new clip remains for inspection")
            return {
                "track_index": track_index,
                "clip_index": clip_index,
                "note_count": len(expected),
                "verified": True,
                "material": material,
            }

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False})
    def create_native_bass(
        recipe: str = "tearout_fm",
        name: str = "",
        bars: int = 4,
        root_midi: int = 29,
        role: str = "call",
        seed: int = 0,
        add_movement: bool = True,
        phrase_style: Optional[str] = None,
    ) -> dict:
        """Build a NEW track with an original native bass patch, matching effects, verified parameters and a Session MIDI phrase. Choose recipes from bass_design_catalog. Preserves existing tracks, tempo and Arrangement; does not start playback. Optional movement requires envelope bridge. Multi-operation build: on failure, a named partial new track remains for inspection."""
        spec = get_recipe(recipe)
        if spec["role"] == "sub" and role == "call":
            role = "sub"
        style = phrase_style or spec["style"]
        material = phrase(style, bars, root_midi, role, seed)
        if len(name) > 120:
            raise ValueError("Track name too long")
        track_name = name or "BASS LAB - " + recipe
        # Validate movement workload before creating tracks.
        motion = spec["movement"]
        if add_movement and motion["shape"] != "duck":
            curve_points(motion["shape"], 0, material["length"], cycle_beats=motion["cycle_beats"])
        with _mutation_lock:
            require(
                "get_sound_design_parameters",
                "set_sound_design_parameters",
                *(["write_clip_envelope"] if add_movement else []),
            )
            uris = [
                resolve_device(d) for d in spec["chain"]
            ]  # All device availability checks before mutation.
            created = send("create_midi_track", {"index": -1})
            idx = created["index"]
            try:
                send("set_track_name", {"track_index": idx, "name": track_name})
                batches = []
                for dindex, (device_spec, uri) in enumerate(zip(spec["chain"], uris)):
                    track_info(idx, track_name)
                    send("load_browser_item", {"track_index": idx, "item_uri": uri})
                    info = None
                    for attempt in range(12):
                        info = track_info(idx, track_name)
                        if len(info["devices"]) == dindex + 1:
                            break
                        time.sleep(0.15)
                    if len(info["devices"]) != dindex + 1:
                        raise RuntimeError(
                            "Unexpected device-chain length after loading " + device_spec["name"]
                        )
                    data = send(
                        "get_sound_design_parameters",
                        {
                            "track_index": idx,
                            "device_index": dindex,
                            "expected_track_name": track_name,
                        },
                    )
                    batches.append(
                        send(
                            "set_sound_design_parameters",
                            {
                                "track_index": idx,
                                "device_index": dindex,
                                "parameters": device_spec["parameters"],
                                "expected_track_name": track_name,
                                "expected_device_name": data["device_name"],
                            },
                        )
                    )
                # Internal helper deliberately avoids reacquiring the mutation lock.
                send(
                    "create_clip",
                    {"track_index": idx, "clip_index": 0, "length": material["length"]},
                )
                send(
                    "set_clip_name",
                    {"track_index": idx, "clip_index": 0, "name": recipe + " - " + role},
                )
                send(
                    "add_notes_to_clip",
                    {"track_index": idx, "clip_index": 0, "notes": material["notes"]},
                )
                actual = send("get_clip_notes", {"track_index": idx, "clip_index": 0})
                if actual["note_count"] != len(material["notes"]):
                    raise RuntimeError("New phrase note count differs on readback")
                automation = None
                if add_movement and motion["shape"] != "duck":
                    matches = [
                        i
                        for i, d in enumerate(spec["chain"])
                        if d["name"] == motion["device"]
                        or (d.get("preset") or "").removesuffix(".adv") == motion["device"]
                    ]
                    automation = movement(
                        idx,
                        0,
                        motion["shape"],
                        matches[0],
                        motion["parameter"],
                        motion["low"],
                        motion["high"],
                        motion["cycle_beats"],
                        0.0625,
                        None,
                        0.5,
                        0.0625,
                        False,
                        track_name,
                    )
                return {
                    "track_index": idx,
                    "track_name": track_name,
                    "recipe": recipe,
                    "verified_parameter_batches": batches,
                    "clip_index": 0,
                    "note_count": len(material["notes"]),
                    "automation": automation,
                    "next": "Audition and refine; clean_sub ducking needs actual kick times. No audio audition was performed by this tool.",
                    "sources": spec["sources"],
                    "provenance": spec["provenance"],
                    "artist_evidence_scope": spec.get("artist_evidence_scope"),
                }
            except Exception as error:
                raise RuntimeError(
                    "Build stopped on new track %d (%s); existing tracks preserved. Partial new track remains: %s"
                    % (idx, track_name, error)
                ) from error

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def inspect_sub_clip(track_index: int, clip_index: int, expected_track_name: str) -> dict:
        """Check a MIDI sub clip for note overlap, register and fundamental frequencies. No audio analysis, no automatic pitch changes, no claims about clipping or phase."""
        track = track_info(track_index, expected_track_name)
        session_clip(track, clip_index)
        data = send("get_clip_notes", {"track_index": track_index, "clip_index": clip_index})
        return inspect_sub_notes(data["notes"])

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def tearout_gun_blueprint(bars: int = 4, root_midi: int = 29, seed: int = 0) -> dict:
        """BassTi tutorial-informed four-layer gun workflow and synchronized triplet MIDI material. Separates timestamped caption evidence from native adaptations. Read-only: does not build routing/racks or claim exact third-party settings. Use tearout_triplet in phrase tools for executable MIDI."""
        return gun_blueprint(bars, root_midi, seed)

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def bass_resampling_workflow() -> dict:
        """Return an honest resampling workflow and exposed-tool limits. This tool does NOT record, render, route or export audio."""
        return {
            "steps": [
                "Keep the sine sub separate from the mid-bass sound-design layer.",
                "Create a sustained MIDI phrase, then write FM/filter/distortion movement on its Session clip.",
                "Audition changes and gain-match before comparing variants.",
                "Record the mid-bass to an audio track in Live using its routing/Resampling controls (manual step).",
                "Chop useful moments, add short fades, and arrange call/response gaps around the drums.",
                "If desired, load the recorded WAV with create_audio_clip for further arrangement.",
            ],
            "automated_here": [
                "native patch construction",
                "MIDI phrases",
                "Session envelopes",
                "named parameter editing",
                "MIDI sub inspection",
            ],
            "manual_here": [
                "audio recording/rendering",
                "audio audition",
                "phase/spectrum/loudness checks",
                "direct Arrangement envelope editing",
            ],
            "sources": [SOURCES["operator"], SOURCES["effects"]],
        }

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def mastering_recipe_catalog(recipe: Optional[str] = None) -> dict:
        """Seven advanced mastering recipes: M/S EQ, selective band dynamics, sub-aware glue, staged peak control, stereo translation, section consistency and delivery QC. Displayed-unit audition settings, primary sources and back-off criteria. Read-only; does not apply a master or measure audio."""
        return mastering_catalog(recipe)

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def preview_mastering_plan(
        profile: str = "tearout_dense",
        measured_lufs: Optional[float] = None,
        measured_true_peak_dbtp: Optional[float] = None,
    ) -> dict:
        """Read-only conditional mastering plan: transparent, tearout_dense, spotify_delivery. Optional measurements must come from an external meter; never inferred. Includes ordered optional stages, delivery ceiling guidance and verification steps. Does not construct a chain, set gain, measure, render or audition audio."""
        return mastering_plan(profile, measured_lufs, measured_true_peak_dbtp)

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def artist_bass_catalog(artist: str = "all") -> dict:
        """Artist-informed bass methods: ALLEYCVT, Subtronics, VULPER and Ray Volpe / Volpetron. Distinguishes direct-interview findings, release metadata and original native patches. VULPER processing is undocumented. Read-only; use create_native_bass separately for the four original patch recipes. No audio analysis, artist-preset loading or exact track reconstruction."""
        return artist_catalog(artist)
